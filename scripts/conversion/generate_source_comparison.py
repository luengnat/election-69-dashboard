#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from ect_api import ECTData
from vote62_api import get_voting_district_code


def load_killernay_party(path: str) -> dict[tuple[str, int], dict[int, int]]:
    by_dist: dict[tuple[str, int], dict[int, int]] = defaultdict(dict)
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            prov = (r.get("จังหวัด") or "").strip()
            dist = int(r.get("เขต") or 0)
            num = int(r.get("หมายเลข") or 0)
            score = int(r.get("คะแนน") or 0)
            by_dist[(prov, dist)][num] = score
    return by_dist


def load_killernay_cons(path: str) -> dict[tuple[str, int], dict[int, int]]:
    by_dist: dict[tuple[str, int], dict[int, int]] = defaultdict(dict)
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            prov = (r.get("จังหวัด") or "").strip()
            dist = int(r.get("เขต") or 0)
            num = int(r.get("หมายเลข") or 0)
            score = int(r.get("คะแนน") or 0)
            by_dist[(prov, dist)][num] = score
    return by_dist


def build_cons_id_map(ect: ECTData) -> dict[tuple[str, int], str]:
    mapping: dict[tuple[str, int], str] = {}
    for cons in ect._constituencies.values():
        if not hasattr(cons, "cons_id"):
            continue
        prov = ect._provinces.get(cons.prov_id)
        if not prov:
            continue
        mapping[(prov.name, int(cons.cons_no))] = cons.cons_id
    return mapping


def mismatch_count(a: dict[int, int], b: dict[int, int]) -> int:
    keys = set(a) | set(b)
    return sum(1 for k in keys if int(a.get(k, 0)) != int(b.get(k, 0)))


def main() -> int:
    ect = ECTData()
    ect.load()
    ect.load_official_results()

    killernay_candidates = [
        Path("/tmp/election-69-OCR-result-codex-latest/data/csv"),
        Path("/tmp/election-69-OCR-result-codex/data/csv"),
    ]
    killernay_base = next((p for p in killernay_candidates if p.exists()), killernay_candidates[0])

    party = load_killernay_party(str(killernay_base / "party_list.csv"))
    cons = load_killernay_cons(str(killernay_base / "constituency.csv"))
    cons_id_map = build_cons_id_map(ect)

    keys = sorted(set(party) | set(cons), key=lambda x: (x[0], x[1]))
    items = []
    for prov, dist in keys:
        cons_id = cons_id_map.get((prov, dist))
        ect_party: dict[int, int] = {}
        ect_cons: dict[int, int] = {}
        ect_valid = None
        if cons_id:
            res = ect.get_official_constituency_results(cons_id)
            if res:
                ect_party = {int(k): int(v) for k, v in (res.get("party_votes") or {}).items()}
                ect_cons = {int(k): int(v) for k, v in (res.get("vote_counts") or {}).items()}
                ect_valid = int(res.get("valid_votes") or 0)

        kp = party.get((prov, dist), {})
        kc = cons.get((prov, dist), {})
        kp_valid = sum(kp.values()) if kp else None
        kc_valid = sum(kc.values()) if kc else None
        ep_valid = sum(ect_party.values()) if ect_party else None
        ec_valid = sum(ect_cons.values()) if ect_cons else None

        items.append(
            {
                "province": prov,
                "district_number": dist,
                "cons_id": cons_id,
                "vote62_has_district_code": bool(get_voting_district_code(prov, dist)),
                "ect_valid_votes": ect_valid,
                "party": {
                    "killernay_valid": kp_valid,
                    "ect_valid": ep_valid,
                    "delta_valid": (kp_valid - ep_valid) if kp_valid is not None and ep_valid is not None else None,
                    "mismatch_count": mismatch_count(kp, ect_party) if kp and ect_party else None,
                },
                "constituency": {
                    "killernay_valid": kc_valid,
                    "ect_valid": ec_valid,
                    "delta_valid": (kc_valid - ec_valid) if kc_valid is not None and ec_valid is not None else None,
                    "mismatch_count": mismatch_count(kc, ect_cons) if kc and ect_cons else None,
                },
            }
        )

    def top(items: list[dict], key: str, section: str, n: int = 25):
        ranked = [x for x in items if x.get(section, {}).get(key) is not None]
        ranked.sort(key=lambda x: abs(x[section][key]), reverse=True)
        return ranked[:n]

    summary = {
        "districts_total": len(items),
        "with_ect": sum(1 for x in items if x.get("cons_id")),
        "with_vote62_district_code": sum(1 for x in items if x.get("vote62_has_district_code")),
        "party_exact_valid": sum(1 for x in items if x["party"]["delta_valid"] == 0),
        "constituency_exact_valid": sum(1 for x in items if x["constituency"]["delta_valid"] == 0),
    }
    payload = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "summary": summary,
        "top_party_delta": top(items, "delta_valid", "party"),
        "top_constituency_delta": top(items, "delta_valid", "constituency"),
        "items": items,
    }

    out = Path("/tmp/e69-dashboard-publish/docs/data/source_comparison_data.json")
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} districts={len(items)}")
    print(f"killernay_base={killernay_base}")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
