#!/usr/bin/env python3
"""
Ballot data validation and ECT comparison.

Contains: detect_discrepancies, format_discrepancy_report,
verify_with_ect_data.
"""

from typing import Optional

from ballot_types import BallotData

try:
    from ect_api import ect_data
    ECT_AVAILABLE = True
except ImportError:
    ECT_AVAILABLE = False

def detect_discrepancies(extracted_data: BallotData, official_data: Optional[dict] = None) -> dict:
    """
    Detect discrepancies between extracted ballot data and official ECT results.
    
    Args:
        extracted_data: BallotData object with extracted votes
        official_data: Optional dict with official vote counts from ECT
        
    Returns:
        Dictionary with discrepancy report
    """
    report = {
        "form_type": extracted_data.form_type,
        "polling_station": extracted_data.polling_station_id,
        "extracted_total": extracted_data.valid_votes,
        "official_total": official_data.get("total", 0) if official_data else None,
        "discrepancies": [],
        "summary": {
            "high_severity": 0,
            "medium_severity": 0,
            "low_severity": 0,
            "matches": 0
        }
    }
    
    # If no official data, return empty report
    if not official_data:
        report["status"] = "pending_official_data"
        return report
    
    # Determine form type and compare accordingly
    if extracted_data.form_category == "party_list":
        # Compare party votes
        official_votes = official_data.get("party_votes", {})
        for party_num_str, extracted_votes in extracted_data.party_votes.items():
            party_num = int(party_num_str)
            official_votes_count = official_votes.get(party_num, 0)
            
            if extracted_votes == official_votes_count:
                report["summary"]["matches"] += 1
            else:
                variance = abs(extracted_votes - official_votes_count)
                variance_pct = (variance / official_votes_count * 100) if official_votes_count > 0 else 100.0
                
                # Determine severity
                if variance_pct > 10:
                    severity = "HIGH"
                    report["summary"]["high_severity"] += 1
                elif variance_pct > 5:
                    severity = "MEDIUM"
                    report["summary"]["medium_severity"] += 1
                else:
                    severity = "LOW"
                    report["summary"]["low_severity"] += 1
                
                # Get party name if available
                party_info = extracted_data.party_info.get(party_num_str, {})
                party_name = party_info.get("name", f"Party #{party_num_str}")
                party_abbr = party_info.get("abbr", "")
                
                report["discrepancies"].append({
                    "type": "party_vote",
                    "party_number": party_num,
                    "party_name": party_name,
                    "party_abbr": party_abbr,
                    "extracted": extracted_votes,
                    "official": official_votes_count,
                    "variance": variance,
                    "variance_pct": f"{variance_pct:.1f}%",
                    "severity": severity
                })
    else:
        # Compare constituency votes
        official_votes = official_data.get("vote_counts", {})
        for position, extracted_votes in extracted_data.vote_counts.items():
            official_votes_count = official_votes.get(position, 0)
            
            if extracted_votes == official_votes_count:
                report["summary"]["matches"] += 1
            else:
                variance = abs(extracted_votes - official_votes_count)
                variance_pct = (variance / official_votes_count * 100) if official_votes_count > 0 else 100.0
                
                # Determine severity
                if variance_pct > 10:
                    severity = "HIGH"
                    report["summary"]["high_severity"] += 1
                elif variance_pct > 5:
                    severity = "MEDIUM"
                    report["summary"]["medium_severity"] += 1
                else:
                    severity = "LOW"
                    report["summary"]["low_severity"] += 1
                
                # Get candidate name if available
                candidate_info = extracted_data.candidate_info.get(position, {})
                candidate_name = candidate_info.get("name", f"Position #{position}")
                
                report["discrepancies"].append({
                    "type": "candidate_vote",
                    "position": position,
                    "candidate_name": candidate_name,
                    "extracted": extracted_votes,
                    "official": official_votes_count,
                    "variance": variance,
                    "variance_pct": f"{variance_pct:.1f}%",
                    "severity": severity
                })
    
    # Overall status
    if report["summary"]["high_severity"] > 0:
        report["status"] = "discrepancies_found_high"
    elif report["summary"]["medium_severity"] > 0:
        report["status"] = "discrepancies_found_medium"
    elif report["summary"]["low_severity"] > 0:
        report["status"] = "discrepancies_found_low"
    else:
        report["status"] = "verified"
    
    return report


def format_discrepancy_report(discrepancy_report: dict) -> str:
    """
    Format a discrepancy report as human-readable text.
    
    Args:
        discrepancy_report: Report dict from detect_discrepancies()
        
    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 70)
    lines.append("BALLOT VERIFICATION REPORT")
    lines.append("=" * 70)
    
    lines.append(f"\nForm Type: {discrepancy_report['form_type']}")
    lines.append(f"Polling Station: {discrepancy_report['polling_station']}")
    
    # Status with emoji
    status = discrepancy_report.get('status', 'unknown')
    status_emoji = {
        'verified': '✓',
        'discrepancies_found_low': '⚠',
        'discrepancies_found_medium': '⚠⚠',
        'discrepancies_found_high': '✗',
        'pending_official_data': '?'
    }.get(status, '?')
    
    status_text = {
        'verified': 'VERIFIED - No discrepancies',
        'discrepancies_found_low': 'LOW SEVERITY discrepancies found',
        'discrepancies_found_medium': 'MEDIUM SEVERITY discrepancies found',
        'discrepancies_found_high': 'HIGH SEVERITY discrepancies found',
        'pending_official_data': 'Waiting for official results'
    }.get(status, 'Unknown status')
    
    lines.append(f"\nStatus: {status_emoji} {status_text}")
    
    # Summary
    summary = discrepancy_report['summary']
    lines.append("\nVerification Summary:")
    lines.append(f"  Verified matches: {summary['matches']}")
    lines.append(f"  Low severity issues: {summary['low_severity']}")
    lines.append(f"  Medium severity issues: {summary['medium_severity']}")
    lines.append(f"  High severity issues: {summary['high_severity']}")
    
    # Discrepancies
    if discrepancy_report['discrepancies']:
        lines.append(f"\nDiscrepancies Detected ({len(discrepancy_report['discrepancies'])} items):")
        lines.append("-" * 70)
        
        for disc in discrepancy_report['discrepancies']:
            if disc['type'] == 'candidate_vote':
                lines.append(f"\nPosition {disc['position']}: {disc['candidate_name']}")
            else:
                lines.append(f"\nParty #{disc['party_number']}: {disc['party_name']} ({disc['party_abbr']})")
            
            lines.append(f"  Extracted: {disc['extracted']} votes")
            lines.append(f"  Official:  {disc['official']} votes")
            lines.append(f"  Variance:  {disc['variance']} votes ({disc['variance_pct']})")
            lines.append(f"  Severity:  {disc['severity']}")
    else:
        lines.append("\n✓ All votes verified successfully!")
    
    lines.append("\n" + "=" * 70)
    
    return "\n".join(lines)


def verify_with_ect_data(ballot_data: BallotData, ect_api_url: str) -> dict:
    """
    Compare extracted ballot data with official ECT API data.
    """

    def add_discrepancy(result_obj: dict, severity: str, disc_type: str, **payload) -> None:
        """Append discrepancy and update severity summary counters."""
        result_obj["discrepancies"].append({
            "type": disc_type,
            "severity": severity,
            **payload,
        })
        counter_key = f"{severity.lower()}_severity"
        if counter_key in result_obj["summary"]:
            result_obj["summary"][counter_key] += 1

    def finalize_status(result_obj: dict, official_checked: bool) -> None:
        """Set overall status based on discrepancy severity."""
        if result_obj["summary"]["high_severity"] > 0:
            result_obj["status"] = "discrepancies_found_high"
        elif result_obj["summary"]["medium_severity"] > 0:
            result_obj["status"] = "discrepancies_found_medium"
        elif result_obj["summary"]["low_severity"] > 0:
            result_obj["status"] = "discrepancies_found_low"
        elif official_checked:
            result_obj["status"] = "verified"
        else:
            result_obj["status"] = "pending_official_data"

    def get_candidate_info(position: int) -> dict:
        """Fetch candidate metadata regardless of int/str key format."""
        return ballot_data.candidate_info.get(position) or ballot_data.candidate_info.get(str(position), {})

    result = {
        "form_type": ballot_data.form_type,
        "polling_station": ballot_data.polling_station_id,
        "ballot_data": {
            "form_type": ballot_data.form_type,
            "form_category": ballot_data.form_category,
            "polling_station": ballot_data.polling_station_id,
            "province": ballot_data.province,
            "constituency_number": ballot_data.constituency_number,
            "polling_unit": ballot_data.polling_unit,
            "total_votes": ballot_data.total_votes,
        },
        "ect_data": {
            "province": None,
            "province_abbr": None,
            "constituency_id": None,
            "constituency_vote_stations": None,
            "vote_counts": {},
            "party_votes": {},
            "total_votes": None,
            "official_results_available": False,
            "candidate_info": {},
            "party_info": {},
        },
        "discrepancies": [],
        "summary": {
            "high_severity": 0,
            "medium_severity": 0,
            "low_severity": 0,
            "matches": 0,
        },
        "status": "pending_ect_data",
    }

    # Add appropriate vote data based on form type
    if ballot_data.form_category == "party_list":
        result["ballot_data"]["party_votes"] = ballot_data.party_votes
    else:
        result["ballot_data"]["vote_counts"] = ballot_data.vote_counts

    if not ECT_AVAILABLE:
        return result

    try:
        official_checked = False
        cons_id = None
        province_valid, canonical_province = ect_data.validate_province_name(ballot_data.province)
        if province_valid and canonical_province:
            result["ect_data"]["province"] = canonical_province
            result["summary"]["matches"] += 1
        else:
            add_discrepancy(
                result,
                "HIGH",
                "province_reference",
                extracted=ballot_data.province,
                expected="valid ECT province",
            )

        province_for_lookup = canonical_province or ballot_data.province
        province_abbr = ect_data.get_province_abbr(province_for_lookup)
        if province_abbr:
            result["ect_data"]["province_abbr"] = province_abbr
            result["summary"]["matches"] += 1
        else:
            add_discrepancy(
                result,
                "HIGH",
                "province_abbr_lookup",
                extracted=province_for_lookup,
                expected="valid province abbreviation",
            )

        # Constituency-level structural checks for forms that contain constituency ID.
        if ballot_data.constituency_number and province_abbr:
            cons_id = f"{province_abbr}_{ballot_data.constituency_number}"
            constituency = ect_data.get_constituency(cons_id)
            result["ect_data"]["constituency_id"] = cons_id
            if constituency:
                result["summary"]["matches"] += 1
                result["ect_data"]["constituency_vote_stations"] = constituency.total_vote_stations
                if ballot_data.polling_unit > 0 and constituency.total_vote_stations > 0:
                    if ballot_data.polling_unit <= constituency.total_vote_stations:
                        result["summary"]["matches"] += 1
                    else:
                        add_discrepancy(
                            result,
                            "HIGH",
                            "polling_unit_range",
                            extracted=ballot_data.polling_unit,
                            expected=f"1-{constituency.total_vote_stations}",
                        )
            else:
                add_discrepancy(
                    result,
                    "HIGH",
                    "constituency_reference",
                    extracted=cons_id,
                    expected="existing ECT constituency",
                )

        # If official constituency results are available, compare extracted votes directly.
        if cons_id:
            official_results = ect_data.get_official_constituency_results(cons_id)
            if official_results:
                official_checked = True
                result["ect_data"]["official_results_available"] = True
                result["ect_data"]["vote_counts"] = official_results.get("vote_counts", {})
                result["ect_data"]["party_votes"] = official_results.get("party_votes", {})
                result["ect_data"]["total_votes"] = official_results.get("total")

                vote_report = detect_discrepancies(ballot_data, official_results)
                result["summary"]["matches"] += vote_report.get("summary", {}).get("matches", 0)
                for discrepancy in vote_report.get("discrepancies", []):
                    result["discrepancies"].append(discrepancy)
                    severity = discrepancy.get("severity", "LOW")
                    counter_key = f"{severity.lower()}_severity"
                    if counter_key in result["summary"]:
                        result["summary"][counter_key] += 1

        if ballot_data.form_category == "party_list":
            for party_no_str, extracted_votes in ballot_data.party_votes.items():
                if not str(party_no_str).isdigit():
                    add_discrepancy(
                        result,
                        "MEDIUM",
                        "party_number_format",
                        extracted=party_no_str,
                        expected="numeric party number",
                    )
                    continue

                party = ect_data.get_party_by_number(int(party_no_str))
                if party:
                    result["summary"]["matches"] += 1
                    result["ect_data"]["party_info"][str(party_no_str)] = {
                        "name": party.name,
                        "abbr": party.abbr,
                        "extracted_votes": extracted_votes,
                    }
                else:
                    add_discrepancy(
                        result,
                        "MEDIUM",
                        "party_reference_missing",
                        party_number=int(party_no_str),
                        extracted_votes=extracted_votes,
                        expected="known ECT party",
                    )
        else:
            for position, extracted_votes in ballot_data.vote_counts.items():
                candidate = ect_data.get_candidate_by_thai_province(
                    ballot_data.province,
                    ballot_data.constituency_number,
                    int(position),
                )
                if not candidate:
                    add_discrepancy(
                        result,
                        "MEDIUM",
                        "candidate_reference_missing",
                        position=int(position),
                        extracted_votes=extracted_votes,
                        expected="known ECT candidate",
                    )
                    continue

                result["summary"]["matches"] += 1
                party = ect_data.get_party_for_candidate(candidate)
                party_abbr = party.abbr if party else ""
                result["ect_data"]["candidate_info"][str(position)] = {
                    "name": candidate.mp_app_name,
                    "party_abbr": party_abbr,
                    "extracted_votes": extracted_votes,
                }

                extracted_candidate = get_candidate_info(int(position))
                extracted_name = extracted_candidate.get("name")
                if extracted_name and extracted_name != candidate.mp_app_name:
                    add_discrepancy(
                        result,
                        "LOW",
                        "candidate_name_mismatch",
                        position=int(position),
                        extracted=extracted_name,
                        expected=candidate.mp_app_name,
                    )
                elif extracted_name:
                    result["summary"]["matches"] += 1

                extracted_party_abbr = extracted_candidate.get("party_abbr")
                if extracted_party_abbr and party_abbr and extracted_party_abbr != party_abbr:
                    add_discrepancy(
                        result,
                        "LOW",
                        "candidate_party_mismatch",
                        position=int(position),
                        extracted=extracted_party_abbr,
                        expected=party_abbr,
                    )
                elif extracted_party_abbr and party_abbr:
                    result["summary"]["matches"] += 1

        finalize_status(result, official_checked)
    except Exception as exc:
        add_discrepancy(
            result,
            "HIGH",
            "ect_verification_error",
            message=str(exc),
        )
        finalize_status(result, official_checked=False)

    return result


