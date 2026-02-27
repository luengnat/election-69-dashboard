#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ect_api import ECTData


TH_TO_ARABIC = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).translate(TH_TO_ARABIC)
    digits = re.findall(r"\d+", text.replace(",", ""))
    return int("".join(digits)) if digits else None


def extract_json(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    src = text.strip()
    if src.startswith("```"):
        src = re.sub(r"^```(?:json)?\s*", "", src, flags=re.IGNORECASE)
        src = re.sub(r"\s*```$", "", src)
    try:
        obj = json.loads(src)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    i = src.find("{")
    j = src.rfind("}")
    if i >= 0 and j > i:
        try:
            obj = json.loads(src[i : j + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def normalize_election_type(raw: Any, form_type: Any, name: Any) -> str:
    text = f"{raw or ''} {form_type or ''} {name or ''}".lower()
    if "(บช)" in text or "party" in text or "บัญชีรายชื่อ" in text:
        return "party_list"
    return "constituency"


def load_killernay_party_ref(path: Path) -> dict[tuple[str, int], dict[int, int]]:
    ref: dict[tuple[str, int], dict[int, int]] = {}
    if not path.exists():
        return ref
    by_key: dict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            province = (row.get("จังหวัด") or "").strip()
            district = to_int(row.get("เขต"))
            if not province or district is None:
                continue
            by_key[(province, district)].append(row)

    for key, rows in by_key.items():
        party_rows: dict[int, list[tuple[str, int]]] = defaultdict(list)
        for row in rows:
            num = to_int(row.get("หมายเลข"))
            score = to_int(row.get("คะแนน"))
            party = (row.get("พรรค") or "").strip()
            if num is None:
                continue
            party_rows[num].append((party, score or 0))

        resolved: dict[int, int] = {}
        for num, candidates in party_rows.items():
            # Prefer concrete party names over placeholders (e.g. "พรรคที่ 1", "UNKNOWN", "ไม่ระบุ").
            non_generic = [
                (name, score)
                for name, score in candidates
                if name and not re.fullmatch(r"(พรรคที่\s*\d+|UNKNOWN|ไม่ระบุ)", name, flags=re.IGNORECASE)
            ]
            chosen = non_generic[0] if non_generic else candidates[0]
            resolved[num] = chosen[1]
        ref[key] = resolved
    return ref


def extract_votes(obj: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    votes = obj.get("votes")
    if isinstance(votes, dict):
        for key, value in votes.items():
            k = to_int(key)
            v = to_int(value)
            if k is None or v is None:
                continue
            out[str(k)] = v

    if out:
        return out

    rows = obj.get("rows")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            num = to_int(row.get("number"))
            val = to_int(row.get("score"))
            if num is None or val is None:
                continue
            out[str(num)] = val
    return out


def normalize_attempt(raw: dict[str, Any]) -> dict[str, Any] | None:
    parsed_obj = None
    if isinstance(raw.get("votes"), dict):
        parsed_obj = raw
    else:
        for key in ("summary", "raw_text"):
            parsed_obj = extract_json(raw.get(key))
            if parsed_obj:
                break
    if not parsed_obj:
        return None

    drive_id = raw.get("drive_id") or parsed_obj.get("drive_id")
    if not drive_id:
        return None

    votes = extract_votes(parsed_obj)
    election_type = normalize_election_type(
        parsed_obj.get("election_type"), parsed_obj.get("form_type") or raw.get("form_type_hint"), raw.get("name")
    )
    return {
        "drive_id": drive_id,
        "drive_url": raw.get("drive_url") or parsed_obj.get("drive_url"),
        "name": raw.get("name") or parsed_obj.get("name"),
        "province": parsed_obj.get("province") or raw.get("province_hint"),
        "district_number": to_int(parsed_obj.get("district_number"))
        or to_int(parsed_obj.get("constituency_number"))
        or to_int(raw.get("district_number_hint")),
        "election_type": election_type,
        "valid_votes": to_int(parsed_obj.get("valid_votes")),
        "invalid_votes": to_int(parsed_obj.get("invalid_votes")),
        "blank_votes": to_int(parsed_obj.get("blank_votes")),
        "votes": votes,
    }


def load_attempts(paths: list[Path]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        if path.suffix.lower() == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                normalized = normalize_attempt(row)
                if normalized:
                    attempts.append(normalized)
            continue

        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(doc, dict) and isinstance(doc.get("items"), list):
            for row in doc["items"]:
                if isinstance(row, dict):
                    normalized = normalize_attempt(row)
                    if normalized:
                        attempts.append(normalized)
        elif isinstance(doc, list):
            for row in doc:
                if isinstance(row, dict):
                    normalized = normalize_attempt(row)
                    if normalized:
                        attempts.append(normalized)
    return attempts


def choose_meta(rows: list[dict[str, Any]], key: str) -> Any:
    values = [r.get(key) for r in rows if r.get(key) not in (None, "")]
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def expected_keys_for_item(item: dict[str, Any], ect_data: ECTData) -> list[int]:
    if item["election_type"] == "party_list":
        return list(range(1, 58))
    province = item.get("province")
    district = item.get("district_number")
    if province and district:
        try:
            ok, canonical = ect_data.validate_province_name(str(province))
            province_name = canonical if ok and canonical else str(province)
            candidates = ect_data.get_candidates_by_thai_province(province_name, int(district))
            positions = sorted(
                {
                    int(c.position)
                    for c in candidates
                    if getattr(c, "position", None) is not None and to_int(c.position) is not None
                }
            )
            if positions:
                return positions
        except Exception:
            pass
    observed = sorted({to_int(k) for r in item["attempts"] for k in r["votes"].keys() if to_int(k) is not None})
    return [k for k in observed if k is not None]


def choose_vote_value(
    key: int,
    observed: list[int],
    attempts_count: int,
    reference_value: int | None,
) -> tuple[int, float, int]:
    if not observed:
        return 0, 0.0, 0
    counter = Counter(observed)
    top_freq = counter.most_common(1)[0][1]
    top_vals = sorted([value for value, freq in counter.items() if freq == top_freq])
    if len(top_vals) == 1:
        selected = top_vals[0]
    elif reference_value is not None:
        selected = sorted(top_vals, key=lambda v: abs(v - reference_value))[0]
    else:
        selected = top_vals[0]
    confidence = top_freq / max(1, attempts_count)
    return selected, confidence, len(observed)


def build_retry_prompt(item: dict[str, Any], focus_keys: list[int]) -> str:
    key_list = ", ".join(str(k) for k in sorted(focus_keys))
    common_header = (
        "Read this election PDF carefully and return STRICT JSON only. "
        "Use Arabic numerals (0-9), not Thai numerals. "
        "Cross-check each numeric vote with the Thai text amount next to it. "
        "If a number is unreadable, set it to null."
    )
    if item["election_type"] == "party_list":
        page_hint = (
            "For form ส.ส. 5/18 (บัญชีรายชื่อ), usually page 1 has party 1-10, "
            "page 2 has 11-34, page 3 has 35-57."
        )
        schema = (
            '{'
            '"drive_id":"...",'
            '"province":"...",'
            '"district_number":0,'
            '"election_type":"party_list",'
            '"valid_votes":0,'
            '"invalid_votes":0,'
            '"blank_votes":0,'
            '"votes":{"1":0,"2":0}'
            "}"
        )
        return (
            f"{common_header}\n"
            f"{page_hint}\n"
            f"Focus only on these party numbers: [{key_list}].\n"
            "Also return valid_votes, invalid_votes, blank_votes from the same form.\n"
            f"Output schema: {schema}"
        )

    schema = (
        '{'
        '"drive_id":"...",'
        '"province":"...",'
        '"district_number":0,'
        '"election_type":"constituency",'
        '"valid_votes":0,'
        '"invalid_votes":0,'
        '"blank_votes":0,'
        '"votes":{"1":0,"2":0}'
        "}"
    )
    return (
        f"{common_header}\n"
        f"Focus only on these candidate numbers: [{key_list}].\n"
        "Also return valid_votes, invalid_votes, blank_votes from the same form.\n"
        f"Output schema: {schema}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True, help="Input json/jsonl files (multiple rounds).")
    parser.add_argument("--output", required=True, help="Merged output JSON path.")
    parser.add_argument("--retry-queue", required=True, help="Retry queue JSON path.")
    parser.add_argument("--retry-prompts-dir", required=True, help="Directory for per-file retry prompt text files.")
    parser.add_argument("--min-confidence", type=float, default=0.6, help="Threshold for stable vote values.")
    parser.add_argument(
        "--killernay-party-csv",
        default="/tmp/election-69-OCR-result-codex/data/csv/party_list.csv",
        help="Reference CSV for party-list tie-break and comparison.",
    )
    args = parser.parse_args()

    input_paths = [Path(p) for p in args.inputs]
    attempts = load_attempts(input_paths)
    by_drive: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        by_drive[attempt["drive_id"]].append(attempt)

    ect_data = ECTData()
    ect_data.load()
    party_ref = load_killernay_party_ref(Path(args.killernay_party_csv))

    merged_items: list[dict[str, Any]] = []
    retry_items: list[dict[str, Any]] = []
    prompt_dir = Path(args.retry_prompts_dir)
    prompt_dir.mkdir(parents=True, exist_ok=True)

    for drive_id, rows in sorted(by_drive.items()):
        item = {
            "drive_id": drive_id,
            "drive_url": choose_meta(rows, "drive_url"),
            "name": choose_meta(rows, "name"),
            "province": choose_meta(rows, "province"),
            "district_number": choose_meta(rows, "district_number"),
            "election_type": choose_meta(rows, "election_type") or "constituency",
            "valid_votes": choose_meta(rows, "valid_votes"),
            "invalid_votes": choose_meta(rows, "invalid_votes"),
            "blank_votes": choose_meta(rows, "blank_votes"),
            "attempts": rows,
        }
        expected_keys = expected_keys_for_item(item, ect_data)
        ref_votes = party_ref.get((str(item.get("province") or ""), int(item["district_number"] or 0)), {})
        if item["election_type"] != "party_list":
            ref_votes = {}

        merged_votes: dict[str, int] = {}
        vote_confidence: dict[str, float] = {}
        vote_presence: dict[str, int] = {}

        for key in expected_keys:
            observed = [r["votes"][str(key)] for r in rows if str(key) in r["votes"]]
            selected, confidence, seen = choose_vote_value(key, observed, len(rows), ref_votes.get(key))
            merged_votes[str(key)] = selected
            vote_confidence[str(key)] = round(confidence, 3)
            vote_presence[str(key)] = seen

        sum_votes = sum(merged_votes.values())
        valid_votes = item.get("valid_votes")
        sum_matches_valid = valid_votes is not None and sum_votes == valid_votes

        ref_mismatches = []
        if ref_votes:
            for key in expected_keys:
                if key not in ref_votes:
                    continue
                merged = merged_votes.get(str(key), 0)
                ref_v = ref_votes[key]
                if merged != ref_v:
                    ref_mismatches.append({"number": key, "merged": merged, "reference": ref_v, "delta": merged - ref_v})

        uncertain_keys = [
            int(k)
            for k, c in vote_confidence.items()
            if c < args.min_confidence or vote_presence.get(k, 0) < max(1, len(rows) // 2)
        ]
        if not sum_matches_valid:
            # Force targeted retry on unstable keys first; if none, ask for top vote rows.
            if not uncertain_keys:
                top_keys = sorted(merged_votes.items(), key=lambda kv: kv[1], reverse=True)[:12]
                uncertain_keys = [int(k) for k, _ in top_keys]

        prompt_path = None
        if uncertain_keys:
            prompt_text = build_retry_prompt(item, uncertain_keys)
            prompt_path = prompt_dir / f"{drive_id}.txt"
            prompt_path.write_text(prompt_text, encoding="utf-8")
            retry_items.append(
                {
                    "drive_id": drive_id,
                    "drive_url": item.get("drive_url"),
                    "name": item.get("name"),
                    "province": item.get("province"),
                    "district_number": item.get("district_number"),
                    "election_type": item.get("election_type"),
                    "focus_keys": sorted(set(uncertain_keys)),
                    "prompt_file": str(prompt_path),
                    "reason": {
                        "sum_matches_valid": sum_matches_valid,
                        "low_confidence_keys": sorted(set(uncertain_keys)),
                        "reference_mismatch_count": len(ref_mismatches),
                    },
                }
            )

        merged_items.append(
            {
                "drive_id": drive_id,
                "drive_url": item.get("drive_url"),
                "name": item.get("name"),
                "province": item.get("province"),
                "district_number": item.get("district_number"),
                "election_type": item.get("election_type"),
                "valid_votes": valid_votes,
                "invalid_votes": item.get("invalid_votes"),
                "blank_votes": item.get("blank_votes"),
                "attempt_count": len(rows),
                "votes": merged_votes,
                "vote_confidence": vote_confidence,
                "sum_votes": sum_votes,
                "sum_matches_valid": sum_matches_valid,
                "reference_mismatches": ref_mismatches,
                "retry_prompt_file": str(prompt_path) if prompt_path else None,
            }
        )

    summary = {
        "inputs": [str(p) for p in input_paths],
        "files_with_attempts": len(by_drive),
        "merged_sum_ok": sum(1 for it in merged_items if it["sum_matches_valid"]),
        "merged_sum_bad": sum(1 for it in merged_items if not it["sum_matches_valid"]),
        "retry_count": len(retry_items),
    }
    Path(args.output).write_text(json.dumps({"summary": summary, "items": merged_items}, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.retry_queue).write_text(json.dumps({"summary": summary, "items": retry_items}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
