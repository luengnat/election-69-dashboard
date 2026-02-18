#!/usr/bin/env python3
"""
Ballot report generation (markdown).

Contains: generate_single_ballot_report, generate_batch_report, save_report,
generate_constituency_report, generate_province_report,
generate_executive_summary.
"""

from typing import Optional

from ballot_types import BallotData, AggregatedResults

def generate_single_ballot_report(ballot_data: BallotData, discrepancy_report: Optional[dict] = None) -> str:
    """
    Generate a comprehensive markdown report for a single ballot.
    
    Args:
        ballot_data: BallotData object with extraction results
        discrepancy_report: Optional discrepancy report from detect_discrepancies()
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    lines = []
    lines.append("# Ballot Verification Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Header section
    lines.append("## Form Information")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Form Type | {ballot_data.form_type} |")
    lines.append(f"| Category | {ballot_data.form_category.title()} |")
    lines.append(f"| Province | {ballot_data.province} |")
    lines.append(f"| Constituency | {ballot_data.constituency_number} |")
    lines.append(f"| District | {ballot_data.district} |")
    lines.append(f"| Polling Unit | {ballot_data.polling_unit} |")
    lines.append(f"| Polling Station | {ballot_data.polling_station_id} |")
    lines.append("")
    
    # Vote totals
    lines.append("## Vote Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Valid Votes | {ballot_data.valid_votes} |")
    lines.append(f"| Invalid Votes | {ballot_data.invalid_votes} |")
    lines.append(f"| Blank Votes | {ballot_data.blank_votes} |")
    lines.append(f"| **Total Votes** | **{ballot_data.total_votes}** |")
    lines.append("")
    
    # Extraction quality
    lines.append("## Extraction Quality")
    lines.append("")
    confidence_level = ballot_data.confidence_details.get("level", "UNKNOWN")
    confidence_score = ballot_data.confidence_score
    
    # Confidence level emoji
    confidence_emoji = {
        "HIGH": "✓",
        "MEDIUM": "⚠",
        "LOW": "⚠",
        "VERY_LOW": "✗"
    }.get(confidence_level, "?")
    
    lines.append(f"**Confidence Level:** {confidence_emoji} {confidence_level} ({confidence_score:.1%})")
    lines.append("")
    
    # Confidence factors
    confidence_details = ballot_data.confidence_details
    if "thai_text_validation" in confidence_details:
        val = confidence_details["thai_text_validation"]
        lines.append(f"- Thai Text Validation: {val['validated']}/{val['total']} ({val['rate']:.1%})")
    
    if "sum_validation" in confidence_details:
        val = confidence_details["sum_validation"]
        match_status = "✓ Matched" if val["match"] else "✗ Mismatch"
        lines.append(f"- Sum Validation: {match_status} (calculated={val['calculated_sum']}, reported={val['reported_valid']})")
    
    if "province_validation" in confidence_details:
        val = confidence_details["province_validation"]
        valid_status = "✓ Valid" if val["valid"] else "✗ Invalid"
        lines.append(f"- Province Validation: {valid_status} ({val['province']})")
    
    lines.append("")
    
    # Votes breakdown
    if ballot_data.form_category == "party_list":
        lines.append("## Party Votes")
        lines.append("")
        if ballot_data.party_votes:
            lines.append("| Party # | Party Name | Abbr | Votes |")
            lines.append("|---------|-----------|------|-------|")
            for party_num_str in sorted(ballot_data.party_votes.keys(), key=lambda x: int(x)):
                votes = ballot_data.party_votes[party_num_str]
                party_info = ballot_data.party_info.get(party_num_str, {})
                party_name = party_info.get("name", "Unknown")
                party_abbr = party_info.get("abbr", "")
                lines.append(f"| {party_num_str} | {party_name} | {party_abbr} | {votes} |")
        lines.append("")
        if ballot_data.page_parties:
            lines.append(f"**Page Parties:** {ballot_data.page_parties}")
            lines.append("")
    else:
        lines.append("## Candidate Votes")
        lines.append("")
        if ballot_data.vote_counts:
            lines.append("| Pos | Candidate Name | Party | Votes |")
            lines.append("|-----|----------------|-------|-------|")
            for position in sorted(ballot_data.vote_counts.keys()):
                votes = ballot_data.vote_counts[position]
                candidate_info = ballot_data.candidate_info.get(position, {})
                candidate_name = candidate_info.get("name", "Unknown")
                party_abbr = candidate_info.get("party_abbr", "")
                lines.append(f"| {position} | {candidate_name} | {party_abbr} | {votes} |")
        lines.append("")
    
    # Discrepancy section
    if discrepancy_report:
        lines.append("## Verification Results")
        lines.append("")
        
        status = discrepancy_report.get("status", "unknown")
        status_emoji = {
            "verified": "✓",
            "discrepancies_found_low": "⚠",
            "discrepancies_found_medium": "⚠⚠",
            "discrepancies_found_high": "✗",
            "pending_ect_data": "?",
            "pending_official_data": "?"
        }.get(status, "?")
        
        status_text = {
            "verified": "VERIFIED - No discrepancies",
            "discrepancies_found_low": "LOW SEVERITY discrepancies found",
            "discrepancies_found_medium": "MEDIUM SEVERITY discrepancies found",
            "discrepancies_found_high": "HIGH SEVERITY discrepancies found",
            "pending_ect_data": "ECT reference unavailable",
            "pending_official_data": "Waiting for official results"
        }.get(status, "Unknown status")
        
        lines.append(f"**Status:** {status_emoji} {status_text}")
        lines.append("")
        
        summary = discrepancy_report["summary"]
        lines.append("**Summary:**")
        lines.append(f"- Verified matches: {summary['matches']}")
        lines.append(f"- Low severity issues: {summary['low_severity']}")
        lines.append(f"- Medium severity issues: {summary['medium_severity']}")
        lines.append(f"- High severity issues: {summary['high_severity']}")
        lines.append("")
        
        if discrepancy_report["discrepancies"]:
            lines.append("### Discrepancies Detected")
            lines.append("")
            lines.append("| Item | Extracted | Official | Variance | Severity |")
            lines.append("|------|-----------|----------|----------|----------|")
            
            for disc in discrepancy_report["discrepancies"]:
                if disc["type"] == "candidate_vote":
                    item = f"Pos {disc['position']}: {disc['candidate_name']}"
                    extracted = disc.get("extracted", "")
                    official = disc.get("official", "")
                    variance = disc.get("variance_pct", "")
                elif disc["type"] == "party_vote":
                    item = f"Party #{disc['party_number']}: {disc['party_name']}"
                    extracted = disc.get("extracted", "")
                    official = disc.get("official", "")
                    variance = disc.get("variance_pct", "")
                else:
                    item = disc["type"]
                    extracted = disc.get("extracted", disc.get("position", disc.get("party_number", "")))
                    official = disc.get("official", disc.get("expected", ""))
                    variance = disc.get("variance_pct", "N/A")
                
                lines.append(f"| {item} | {extracted} | {official} | {variance} | {disc.get('severity', '')} |")
            
            lines.append("")
    
    # Footer
    lines.append("---")
    lines.append(f"*Source File:* {ballot_data.source_file}")
    lines.append("")
    
    return "\n".join(lines)


def generate_batch_report(results: list[dict], ballot_data_list: list[BallotData]) -> str:
    """
    Generate a summary report for a batch of ballots.
    
    Args:
        results: List of discrepancy report dicts
        ballot_data_list: List of BallotData objects
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    lines = []
    lines.append("# Batch Ballot Verification Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Overall statistics
    total_ballots = len(results)
    verified = sum(1 for r in results if r.get("status") == "verified")
    low_severity = sum(1 for r in results if r.get("status") == "discrepancies_found_low")
    medium_severity = sum(1 for r in results if r.get("status") == "discrepancies_found_medium")
    high_severity = sum(1 for r in results if r.get("status") == "discrepancies_found_high")
    
    accuracy_rate = (verified / total_ballots * 100) if total_ballots > 0 else 0
    
    lines.append("## Overall Statistics")
    lines.append("")
    lines.append("| Metric | Count | Percentage |")
    lines.append("|--------|-------|-----------|")
    lines.append(f"| Total Ballots | {total_ballots} | 100% |")
    lines.append(f"| Verified (No Issues) | {verified} | {verified/total_ballots*100:.1f}% |")
    lines.append(f"| Low Severity Issues | {low_severity} | {low_severity/total_ballots*100:.1f}% |")
    lines.append(f"| Medium Severity Issues | {medium_severity} | {medium_severity/total_ballots*100:.1f}% |")
    lines.append(f"| High Severity Issues | {high_severity} | {high_severity/total_ballots*100:.1f}% |")
    lines.append("")
    
    # Accuracy indicator
    if accuracy_rate >= 95:
        accuracy_emoji = "✓✓✓"
        accuracy_text = "Excellent"
    elif accuracy_rate >= 90:
        accuracy_emoji = "✓✓"
        accuracy_text = "Good"
    elif accuracy_rate >= 80:
        accuracy_emoji = "✓"
        accuracy_text = "Acceptable"
    else:
        accuracy_emoji = "✗"
        accuracy_text = "Poor"
    
    lines.append(f"**Verification Accuracy:** {accuracy_emoji} {accuracy_text} ({accuracy_rate:.1f}%)")
    lines.append("")
    
    # Form type breakdown
    if ballot_data_list:
        form_types = {}
        constituencies = {}
        provinces = {}
        
        for ballot in ballot_data_list:
            form_type = ballot.form_type
            form_types[form_type] = form_types.get(form_type, 0) + 1
            
            if ballot.constituency_number:
                cons_key = f"{ballot.province} - Constituency {ballot.constituency_number}"
                constituencies[cons_key] = constituencies.get(cons_key, 0) + 1
            
            if ballot.province:
                provinces[ballot.province] = provinces.get(ballot.province, 0) + 1
        
        if form_types:
            lines.append("## Form Type Breakdown")
            lines.append("")
            lines.append("| Form Type | Count |")
            lines.append("|-----------|-------|")
            for form_type, count in sorted(form_types.items()):
                lines.append(f"| {form_type} | {count} |")
            lines.append("")
        
        if provinces:
            lines.append("## Province Breakdown")
            lines.append("")
            lines.append("| Province | Count |")
            lines.append("|----------|-------|")
            for province, count in sorted(provinces.items()):
                lines.append(f"| {province} | {count} |")
            lines.append("")
    
    # High severity issues summary
    high_severity_items = []
    for i, result in enumerate(results):
        if result.get("status") == "discrepancies_found_high":
            for disc in result.get("discrepancies", []):
                if disc.get("severity") == "HIGH":
                    high_severity_items.append({
                        "ballot_index": i,
                        "station": result.get("polling_station", "Unknown"),
                        "discrepancy": disc
                    })
    
    if high_severity_items:
        lines.append("## High Severity Issues")
        lines.append("")
        lines.append(f"> **⚠ {len(high_severity_items)} high-severity discrepancies detected across batch**")
        lines.append("")
        lines.append("| Polling Station | Item | Extracted | Official | Variance |")
        lines.append("|-----------------|------|-----------|----------|----------|")
        for item in high_severity_items[:10]:  # Show top 10
            disc = item["discrepancy"]
            if disc["type"] == "candidate_vote":
                item_name = f"Pos {disc['position']}: {disc['candidate_name']}"
                extracted = disc.get("extracted", "")
                official = disc.get("official", "")
                variance = disc.get("variance_pct", "")
            elif disc["type"] == "party_vote":
                item_name = f"Party #{disc['party_number']}: {disc['party_name']}"
                extracted = disc.get("extracted", "")
                official = disc.get("official", "")
                variance = disc.get("variance_pct", "")
            else:
                item_name = disc["type"]
                extracted = disc.get("extracted", disc.get("position", disc.get("party_number", "")))
                official = disc.get("official", disc.get("expected", ""))
                variance = disc.get("variance_pct", "N/A")
            
            lines.append(f"| {item['station']} | {item_name} | {extracted} | {official} | {variance} |")
        
        if len(high_severity_items) > 10:
            lines.append(f"| ... | *{len(high_severity_items) - 10} more issues* | | | |")
        
        lines.append("")
    
    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    if high_severity > 0:
        lines.append("⚠ **Manual Review Required**")
        lines.append("")
        lines.append(f"- {high_severity} ballot(s) with high-severity discrepancies")
        lines.append("- Review extracted data against source documents")
        lines.append("- Verify against official ECT results")
        lines.append("- Investigate potential OCR errors or data entry issues")
    elif medium_severity > 0:
        lines.append("⚠ **Quality Check Recommended**")
        lines.append("")
        lines.append(f"- {medium_severity} ballot(s) with medium-severity discrepancies")
        lines.append("- Cross-check with official results")
        lines.append("- Consider re-extraction if discrepancies exceed 5%")
    else:
        lines.append("✓ **No Action Required**")
        lines.append("")
        lines.append("- All ballots verified successfully")
        lines.append(f"- Accuracy rate: {accuracy_rate:.1f}%")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    return "\n".join(lines)


def save_report(report_content: str, output_path: str) -> bool:
    """
    Save report content to a markdown file.
    
    Args:
        report_content: Markdown report string
        output_path: Path to save the report
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"✓ Report saved to: {output_path}")
        return True
    except Exception as e:
        print(f"✗ Error saving report: {e}")
        return False


def generate_constituency_report(agg: AggregatedResults) -> str:
    """
    Generate a detailed markdown report for aggregated constituency results.
    
    Args:
        agg: AggregatedResults object with aggregated data
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    lines = []
    lines.append("# Constituency Results Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Header
    lines.append("## Constituency Information")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Province | {agg.province} |")
    lines.append(f"| Constituency | {agg.constituency} |")
    lines.append(f"| Constituency # | {agg.constituency_no} |")
    lines.append("")
    
    # Data collection status
    lines.append("## Data Collection Status")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Ballots Processed | {agg.ballots_processed} |")
    lines.append(f"| Polling Units Reporting | {agg.polling_units_reporting} |")
    lines.append(f"| Reporting Rate | {float(agg.turnout_rate or 0):.1f}% |")
    lines.append(f"| Form Types Used | {', '.join(agg.form_types)} |")
    lines.append("")
    
    # Vote totals
    lines.append("## Vote Totals")
    lines.append("")
    lines.append("| Category | Votes |")
    lines.append("|----------|-------|")
    lines.append(f"| Valid Votes | {agg.valid_votes_total} |")
    lines.append(f"| Invalid Votes | {agg.invalid_votes_total} |")
    lines.append(f"| Blank Votes | {agg.blank_votes_total} |")
    lines.append(f"| **Overall Total** | **{agg.overall_total}** |")
    lines.append("")
    
    # Quality metrics
    lines.append("## Data Quality")
    lines.append("")
    confidence_emoji = {
        True: "✓",
        False: "⚠"
    }.get(agg.aggregated_confidence >= 0.95, "?")
    
    lines.append(f"**Aggregated Confidence:** {confidence_emoji} {agg.aggregated_confidence:.1%}")
    lines.append(f"**Discrepancy Rate:** {agg.discrepancy_rate:.1%}")
    lines.append(f"**Ballots with Issues:** {agg.ballots_with_discrepancies}/{agg.ballots_processed}")
    lines.append("")
    
    # Results table
    is_party_list = bool(agg.party_totals)
    
    if is_party_list:
        lines.append("## Party Results")
        lines.append("")
        lines.append("| Party # | Party Name | Abbr | Votes | Percentage |")
        lines.append("|---------|-----------|------|-------|-----------|")
        
        # Sort by votes descending
        sorted_results = sorted(agg.party_totals.items(), key=lambda x: x[1], reverse=True)
        for party_num_str, votes in sorted_results:
            info = agg.party_info.get(party_num_str, {})
            party_name = info.get("name", "Unknown")
            abbr = info.get("abbr", "")
            percentage = (votes / agg.valid_votes_total * 100) if agg.valid_votes_total > 0 else 0
            lines.append(f"| {party_num_str} | {party_name} | {abbr} | {votes} | {percentage:.2f}% |")
        
        lines.append("")
    else:
        lines.append("## Candidate Results")
        lines.append("")
        lines.append("| Pos | Candidate Name | Party | Votes | Percentage |")
        lines.append("|-----|----------------|-------|-------|-----------|")
        
        # Sort by votes descending
        sorted_results = sorted(agg.candidate_totals.items(), key=lambda x: x[1], reverse=True)
        for position, votes in sorted_results:
            info = agg.candidate_info.get(position, {})
            candidate_name = info.get("name", "Unknown")
            party = info.get("party_abbr", "")
            percentage = (votes / agg.valid_votes_total * 100) if agg.valid_votes_total > 0 else 0
            lines.append(f"| {position} | {candidate_name} | {party} | {votes} | {percentage:.2f}% |")
        
        lines.append("")
    
    # Winners
    if agg.winners:
        lines.append("## Winners")
        lines.append("")
        for i, winner in enumerate(agg.winners[:3], 1):
            if is_party_list:
                lines.append(f"**#{i}** {winner['name']} ({winner['abbr']})")
                lines.append(f"  - Votes: {winner['votes']}")
                lines.append(f"  - Percentage: {winner['percentage']}")
            else:
                lines.append(f"**#{i}** {winner['name']} ({winner['party']})")
                lines.append(f"  - Votes: {winner['votes']}")
                lines.append(f"  - Percentage: {winner['percentage']}")
            lines.append("")
    
    # Source information
    lines.append("## Source Information")
    lines.append("")
    lines.append("**Ballots Included:**")
    for source in agg.source_ballots:
        lines.append(f"- {source}")
    lines.append("")
    
    # Footer
    lines.append("---")
    lines.append("")
    
    return "\n".join(lines)


def generate_province_report(province_results: list[AggregatedResults], anomalies: list[dict]) -> str:
    """
    Generate a comprehensive province-level report.
    
    Args:
        province_results: List of AggregatedResults for all constituencies in province
        anomalies: List of anomaly dicts from detect_anomalous_constituencies()
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    if not province_results:
        return "No results to report"
    
    province_name = province_results[0].province
    
    lines = []
    lines.append("# Province Electoral Report")
    lines.append("")
    lines.append(f"**Province:** {province_name}")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Overview
    lines.append("## Overview")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Constituencies Reporting | {len(province_results)} |")
    lines.append(f"| Total Valid Votes | {sum(r.valid_votes_total for r in province_results)} |")
    lines.append(f"| Total Invalid Votes | {sum(r.invalid_votes_total for r in province_results)} |")
    lines.append(f"| Overall Total Votes | {sum(r.overall_total for r in province_results)} |")
    lines.append(f"| Average Confidence | {(sum(r.aggregated_confidence for r in province_results) / len(province_results) * 100):.1f}% |")
    lines.append("")
    
    # Data quality
    lines.append("## Data Quality Summary")
    lines.append("")
    high_conf = sum(1 for r in province_results if r.aggregated_confidence >= 0.95)
    med_conf = sum(1 for r in province_results if 0.85 <= r.aggregated_confidence < 0.95)
    low_conf = sum(1 for r in province_results if r.aggregated_confidence < 0.85)
    
    lines.append("**Confidence Levels:**")
    lines.append(f"- High (95%+): {high_conf} constituencies")
    lines.append(f"- Medium (85-95%): {med_conf} constituencies")
    lines.append(f"- Low (<85%): {low_conf} constituencies")
    lines.append("")
    
    # Anomalies in this province
    province_anomalies = [a for a in anomalies if province_name in a["constituency"]]
    if province_anomalies:
        lines.append(f"**Anomalies Detected:** {len(province_anomalies)} constituency/ies")
        lines.append("")
    
    # Constituency breakdown
    lines.append("## Constituency Results")
    lines.append("")
    lines.append("| # | Constituency | Valid Votes | Invalid | Confidence | Status |")
    lines.append("|---|--------------|------------|---------|-----------|--------|")
    
    for i, result in enumerate(province_results, 1):
        # Determine status
        if result.aggregated_confidence >= 0.95:
            status = "✓"
        elif result.aggregated_confidence >= 0.85:
            status = "⚠"
        else:
            status = "✗"
        
        # Check for anomalies
        has_anomaly = any(result.constituency in a["constituency"] for a in province_anomalies)
        if has_anomaly:
            status += " ⚠"
        
        lines.append(f"| {i} | {result.constituency} | {result.valid_votes_total} | {result.invalid_votes_total} | {result.aggregated_confidence:.0%} | {status} |")
    
    lines.append("")
    
    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    if low_conf > 0 or province_anomalies:
        if low_conf > 0:
            lines.append(f"⚠ **{low_conf}** constituency/ies with confidence <85%. Manual review recommended.")
        if province_anomalies:
            lines.append(f"⚠ **{len(province_anomalies)}** constituency/ies with detected anomalies.")
        if high_conf == len(province_results):
            lines.append("✓ All other constituencies show good data quality.")
    else:
        lines.append("✓ All constituencies show good data quality.")
    
    lines.append("")
    
    return "\n".join(lines)


def generate_executive_summary(
    all_results: list[AggregatedResults],
    anomalies: list[dict],
    provinces: Optional[list[str]] = None
) -> str:
    """
    Generate an executive summary report.
    
    Args:
        all_results: All AggregatedResults from all constituencies
        anomalies: All detected anomalies
        provinces: Optional list of provinces (auto-detected if None)
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    if not all_results:
        return "No results to summarize"
    
    # Detect provinces if not provided
    if provinces is None:
        provinces = sorted(set(r.province for r in all_results))
    
    lines = []
    lines.append("# Electoral Results - Executive Summary")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Key statistics
    total_valid = sum(r.valid_votes_total for r in all_results)
    total_invalid = sum(r.invalid_votes_total for r in all_results)
    total_blank = sum(r.blank_votes_total for r in all_results)
    total_votes = sum(r.overall_total for r in all_results)
    avg_confidence = (sum(r.aggregated_confidence for r in all_results) / len(all_results)) if all_results else 0
    
    lines.append("## Key Statistics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total Constituencies | {len(all_results)} |")
    lines.append(f"| Total Provinces | {len(provinces)} |")
    lines.append(f"| Total Valid Votes | {total_valid:,} |")
    lines.append(f"| Total Invalid Votes | {total_invalid:,} |")
    lines.append(f"| Total Blank Votes | {total_blank:,} |")
    lines.append(f"| **Overall Total** | **{total_votes:,}** |")
    lines.append(f"| Average Confidence | {avg_confidence:.1%} |")
    lines.append("")
    
    # Data quality assessment
    lines.append("## Data Quality Assessment")
    lines.append("")
    
    if avg_confidence >= 0.95:
        quality_rating = "EXCELLENT"
        quality_emoji = "✓✓✓"
    elif avg_confidence >= 0.85:
        quality_rating = "GOOD"
        quality_emoji = "✓✓"
    elif avg_confidence >= 0.75:
        quality_rating = "ACCEPTABLE"
        quality_emoji = "✓"
    else:
        quality_rating = "POOR"
        quality_emoji = "✗"
    
    lines.append(f"**Overall Rating:** {quality_emoji} {quality_rating}")
    lines.append(f"**Average Confidence:** {avg_confidence:.1%}")
    lines.append("")
    
    # Province summary
    lines.append("## By Province")
    lines.append("")
    lines.append("| Province | Constituencies | Valid Votes | Avg Confidence |")
    lines.append("|----------|---|---|---|")
    
    for province in provinces:
        prov_results = [r for r in all_results if r.province == province]
        if prov_results:
            prov_valid = sum(r.valid_votes_total for r in prov_results)
            prov_conf = sum(r.aggregated_confidence for r in prov_results) / len(prov_results)
            lines.append(f"| {province} | {len(prov_results)} | {prov_valid:,} | {prov_conf:.1%} |")
    
    lines.append("")
    
    # Top winners (if constituency results)
    is_party_list = bool(all_results[0].party_totals) if all_results else False
    if not is_party_list and all_results:
        lines.append("## Top Candidates Overall")
        lines.append("")
        
        # Aggregate all candidates
        all_winners = []
        for result in all_results:
            for winner in result.winners:
                all_winners.append({
                    "name": winner["name"],
                    "province": result.province,
                    "votes": winner["votes"],
                    "percentage": winner["percentage"]
                })
        
        # Sort by votes
        top_winners = sorted(all_winners, key=lambda x: x["votes"], reverse=True)[:10]
        
        lines.append("| Rank | Candidate | Province | Votes | Percentage |")
        lines.append("|------|-----------|----------|-------|-----------|")
        
        for i, winner in enumerate(top_winners, 1):
            lines.append(f"| {i} | {winner['name']} | {winner['province']} | {winner['votes']:,} | {winner['percentage']} |")
        
        lines.append("")
    
    # Issues and recommendations
    lines.append("## Issues & Recommendations")
    lines.append("")
    
    if anomalies:
        lines.append(f"⚠ **{len(anomalies)}** constituency/ies with detected anomalies")
        lines.append("")
    
    high_anomalies = [a for a in anomalies if a["severity"] == "HIGH"]
    medium_anomalies = [a for a in anomalies if a["severity"] == "MEDIUM"]
    
    if high_anomalies:
        lines.append(f"**CRITICAL ISSUES ({len(high_anomalies)}):**")
        for anom in high_anomalies[:5]:
            lines.append(f"- {anom['constituency']}")
        lines.append("")
    
    if medium_anomalies:
        lines.append(f"**NEEDS REVIEW ({len(medium_anomalies)}):**")
        for anom in medium_anomalies[:5]:
            lines.append(f"- {anom['constituency']}")
        lines.append("")
    
    # Final recommendations
    if avg_confidence < 0.85:
        lines.append("⚠ **Low average confidence.** Consider re-verification of data.")
    elif len(anomalies) > len(all_results) * 0.2:
        lines.append("⚠ **High anomaly rate.** Manual review of flagged constituencies recommended.")
    else:
        lines.append("✓ **Data quality acceptable.** Proceed with standard verification process.")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    return "\n".join(lines)


