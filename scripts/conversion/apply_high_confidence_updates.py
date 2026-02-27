#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CandidateEval:
    row_key: tuple[str, int, str]
    improve_score: float
    current_score: float
    new_score: float
    coherent: bool
    current_coherence_gap: int | None
    candidate_coherence_gap: int | None
    dropped_keys: int
    candidate: dict[str, Any]


def _num(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(float(v))
    except Exception:
        return None


def _votes_map(v: Any) -> dict[str, int]:
    if not isinstance(v, dict):
        return {}
    out: dict[str, int] = {}
    for k, val in v.items():
        n = _num(val)
        if n is None:
            continue
        out[str(k)] = n
    return out


def _coherence_gap(valid: int | None, votes: dict[str, int]) -> int | None:
    if valid is None or not votes:
        return None
    return abs(sum(votes.values()) - valid)


def _row_score(
    row: dict[str, Any],
    valid: int | None,
    votes: dict[str, int],
    weight_ect: float,
    weight_killernay: float,
    weight_vote62: float,
) -> float:
    # Lower score = closer to trusted references.
    refs = []
    for src, w in (("ect", weight_ect), ("killernay", weight_killernay), ("vote62", weight_vote62)):
        if w <= 0:
            continue
        ref_valid = _num(((row.get("sources") or {}).get(src) or {}).get("valid_votes"))
        if ref_valid is not None and valid is not None:
            refs.append((abs(valid - ref_valid), w))
    score = sum(d * w for d, w in refs)

    # Coherence penalty: votes sum should align with valid_votes.
    if valid is not None and votes:
        score += 3.0 * abs(sum(votes.values()) - valid)
    return float(score)


def _normalize_key(row: dict[str, Any]) -> tuple[str, int, str] | None:
    province = str(row.get("province") or "").strip()
    district = _num(row.get("district_number"))
    form = str(row.get("form_type") or row.get("election_type") or "").strip()
    if not province or district is None or not form:
        return None
    return province, district, form


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply high-confidence score updates to dashboard data")
    ap.add_argument("--dashboard-json", default="/tmp/e69-dashboard-publish/docs/data/district_dashboard_data.json")
    ap.add_argument(
        "--candidate-json",
        action="append",
        default=[
            "/Users/nat/dev/election/tmp_expand60_parsed.json",
            "/Users/nat/dev/election/tmp_expand60b_parsed.json",
            "/Users/nat/dev/election/tmp_expand60c_parsed.json",
        ],
    )
    ap.add_argument("--min-improve", type=float, default=2000.0, help="Minimum score improvement required")
    ap.add_argument("--max-dropped-keys", type=int, default=1)
    ap.add_argument("--max-candidate-coherence-gap", type=int, default=1)
    ap.add_argument("--min-current-coherence-gap-for-override", type=int, default=25)
    ap.add_argument("--weight-ect", type=float, default=1.0)
    ap.add_argument("--weight-killernay", type=float, default=1.0)
    ap.add_argument("--weight-vote62", type=float, default=0.35)
    ap.add_argument("--report-json", default="/Users/nat/dev/election/high_confidence_update_report.json")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    dpath = Path(args.dashboard_json)
    data = json.loads(dpath.read_text(encoding="utf-8"))
    items = data.get("items", [])
    by_key: dict[tuple[str, int, str], dict[str, Any]] = {}
    for r in items:
        k = _normalize_key(r)
        if k is not None:
            by_key[k] = r

    candidates_by_key: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    for cpath in args.candidate_json:
        p = Path(cpath)
        if not p.exists():
            continue
        payload = json.loads(p.read_text(encoding="utf-8"))
        arr = payload.get("items", []) if isinstance(payload, dict) else []
        for c in arr:
            # normalize source key names
            c_norm = dict(c)
            c_norm["form_type"] = c.get("election_type") or c.get("form_type")
            k = _normalize_key(c_norm)
            if k is None or k not in by_key:
                continue
            candidates_by_key.setdefault(k, []).append(c_norm)

    evals: list[CandidateEval] = []
    for k, cands in candidates_by_key.items():
        row = by_key[k]
        cur_valid = _num(row.get("valid_votes_extracted"))
        cur_votes = _votes_map(row.get("votes"))
        cur_gap = _coherence_gap(cur_valid, cur_votes)
        cur_score = _row_score(
            row, cur_valid, cur_votes, args.weight_ect, args.weight_killernay, args.weight_vote62
        )

        best_eval: CandidateEval | None = None
        for c in cands:
            new_valid = _num(c.get("valid_votes"))
            new_votes = _votes_map(c.get("votes"))
            new_gap = _coherence_gap(new_valid, new_votes)
            dropped = len(c.get("dropped_vote_keys") or [])
            coherent = (
                new_valid is not None
                and bool(new_votes)
                and new_gap is not None
                and new_gap <= args.max_candidate_coherence_gap
            )
            new_score = _row_score(
                row, new_valid, new_votes, args.weight_ect, args.weight_killernay, args.weight_vote62
            )
            improve = cur_score - new_score
            ev = CandidateEval(
                row_key=k,
                improve_score=improve,
                current_score=cur_score,
                new_score=new_score,
                coherent=coherent,
                current_coherence_gap=cur_gap,
                candidate_coherence_gap=new_gap,
                dropped_keys=dropped,
                candidate=c,
            )
            if best_eval is None or ev.new_score < best_eval.new_score:
                best_eval = ev
        if best_eval is not None:
            evals.append(best_eval)

    selected: list[CandidateEval] = []
    for ev in evals:
        if not ev.coherent or ev.dropped_keys > args.max_dropped_keys:
            continue
        # Path A: references support the update.
        by_ref = ev.improve_score >= args.min_improve
        # Path B: coherence override (candidate coherent, current clearly incoherent).
        by_coherence = (
            ev.current_coherence_gap is not None
            and ev.current_coherence_gap >= args.min_current_coherence_gap_for_override
            and (ev.candidate_coherence_gap is not None and ev.candidate_coherence_gap <= args.max_candidate_coherence_gap)
        )
        if by_ref or by_coherence:
            selected.append(ev)

    applied = []
    if args.apply and selected:
        for ev in selected:
            row = by_key[ev.row_key]
            c = ev.candidate
            row["votes"] = _votes_map(c.get("votes"))
            if _num(c.get("valid_votes")) is not None:
                row["valid_votes_extracted"] = int(_num(c.get("valid_votes")) or 0)
            if _num(c.get("invalid_votes")) is not None:
                row["invalid_votes"] = int(_num(c.get("invalid_votes")) or 0)
            if _num(c.get("blank_votes")) is not None:
                row["blank_votes"] = int(_num(c.get("blank_votes")) or 0)
            row["updated_by"] = "high_confidence_rule"
            row["update_reason"] = f"improve_score={ev.improve_score:.1f}"

            # refresh compare fields
            read_valid = _num(row.get("valid_votes_extracted"))
            cmp = row.setdefault("compare", {})
            for src, key in (
                ("ect", "delta_valid_ect"),
                ("vote62", "delta_valid_vote62"),
                ("killernay", "delta_valid_killernay"),
            ):
                ref = _num(((row.get("sources") or {}).get(src) or {}).get("valid_votes"))
                cmp[key] = (read_valid - ref) if (read_valid is not None and ref is not None) else None
            applied.append(
                {
                    "province": ev.row_key[0],
                    "district_number": ev.row_key[1],
                    "form_type": ev.row_key[2],
                    "improve_score": round(ev.improve_score, 2),
                }
            )

        dpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "dashboard_json": str(dpath),
        "candidate_files": args.candidate_json,
        "min_improve": args.min_improve,
        "max_dropped_keys": args.max_dropped_keys,
        "max_candidate_coherence_gap": args.max_candidate_coherence_gap,
        "min_current_coherence_gap_for_override": args.min_current_coherence_gap_for_override,
        "weights": {
            "ect": args.weight_ect,
            "killernay": args.weight_killernay,
            "vote62": args.weight_vote62,
        },
        "evaluated_keys": len(evals),
        "selected_updates": len(selected),
        "applied_updates": len(applied),
        "selected_preview": [
            {
                "province": ev.row_key[0],
                "district_number": ev.row_key[1],
                "form_type": ev.row_key[2],
                "improve_score": round(ev.improve_score, 2),
                "coherent": ev.coherent,
                "dropped_keys": ev.dropped_keys,
            }
            for ev in sorted(selected, key=lambda x: x.improve_score, reverse=True)[:50]
        ],
        "applied": applied,
    }
    Path(args.report_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
