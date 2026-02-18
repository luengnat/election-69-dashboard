#!/usr/bin/env python3
"""
Ballot result aggregation and statistical analysis.

Contains: aggregate_ballot_results, aggregate_constituency,
analyze_constituency_discrepancies, generate_discrepancy_summary,
calculate_vote_statistics, detect_anomalous_constituencies,
generate_anomaly_report.
"""

from typing import Optional

from ballot_types import BallotData, AggregatedResults

def aggregate_ballot_results(ballot_data_list: list[BallotData]) -> dict[tuple, AggregatedResults]:
    """
    Aggregate ballot results by constituency.
    
    Args:
        ballot_data_list: List of BallotData objects from multiple polling stations
        
    Returns:
        Dictionary mapping (province, constituency_no) to AggregatedResults
    """
    # Group ballots by constituency
    grouped = {}
    
    for ballot in ballot_data_list:
        key = (ballot.province, ballot.constituency_number)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(ballot)
    
    # Aggregate each constituency
    results = {}
    for (province, cons_no), ballots in grouped.items():
        results[(province, cons_no)] = aggregate_constituency(province, cons_no, ballots)
    
    return results


def aggregate_constituency(province: str, constituency_no: int, ballots: list[BallotData]) -> AggregatedResults:
    """
    Aggregate ballot results for a single constituency.
    
    Args:
        province: Province name
        constituency_no: Constituency number
        ballots: List of BallotData objects for this constituency
        
    Returns:
        AggregatedResults with aggregated votes and analysis
    """
    if not ballots:
        return AggregatedResults(province=province, constituency=province, constituency_no=constituency_no)
    
    # Determine if this is constituency or party-list based on first ballot
    is_party_list = ballots[0].form_category == "party_list"
    
    # Initialize aggregation
    agg = AggregatedResults(
        province=province,
        constituency=ballots[0].district or province,
        constituency_no=constituency_no,
        ballots_processed=len(ballots),
    )
    
    # Aggregate votes
    if is_party_list:
        # Party-list aggregation
        party_vote_counts = {}
        party_info_map = {}
        
        for ballot in ballots:
            # Add votes
            for party_num_str, votes in ballot.party_votes.items():
                party_vote_counts[party_num_str] = party_vote_counts.get(party_num_str, 0) + votes
            
            # Collect party info
            for party_num_str, info in ballot.party_info.items():
                if party_num_str not in party_info_map:
                    party_info_map[party_num_str] = info
        
        agg.party_totals = party_vote_counts
        agg.party_info = party_info_map
        
    else:
        # Constituency aggregation
        candidate_vote_counts = {}
        candidate_info_map = {}
        
        for ballot in ballots:
            # Add votes
            for position, votes in ballot.vote_counts.items():
                candidate_vote_counts[position] = candidate_vote_counts.get(position, 0) + votes
            
            # Collect candidate info
            for position, info in ballot.candidate_info.items():
                if position not in candidate_info_map:
                    candidate_info_map[position] = info
        
        agg.candidate_totals = candidate_vote_counts
        agg.candidate_info = candidate_info_map
    
    # Aggregate vote categories
    valid_total = 0
    invalid_total = 0
    blank_total = 0
    
    for ballot in ballots:
        valid_total += ballot.valid_votes
        invalid_total += ballot.invalid_votes
        blank_total += ballot.blank_votes
    
    agg.valid_votes_total = valid_total
    agg.invalid_votes_total = invalid_total
    agg.blank_votes_total = blank_total
    agg.overall_total = valid_total + invalid_total + blank_total
    
    # Count polling units
    polling_units = set()
    for ballot in ballots:
        polling_units.add(ballot.polling_unit)
    agg.polling_units_reporting = len(polling_units)
    
    # Calculate aggregated confidence
    if ballots:
        avg_confidence = sum(b.confidence_score for b in ballots) / len(ballots)
        agg.aggregated_confidence = avg_confidence
    
    # Track discrepancies
    agg.ballots_with_discrepancies = sum(1 for b in ballots if b.confidence_score < 0.9)
    agg.discrepancy_rate = (agg.ballots_with_discrepancies / len(ballots)) if ballots else 0.0
    
    # Calculate winners
    if is_party_list:
        # Sort parties by votes
        sorted_parties = sorted(agg.party_totals.items(), key=lambda x: x[1], reverse=True)
        for party_num_str, votes in sorted_parties[:5]:  # Top 5 parties
            info = agg.party_info.get(party_num_str, {})
            percentage = (votes / agg.valid_votes_total * 100) if agg.valid_votes_total > 0 else 0
            agg.winners.append({
                "party_number": party_num_str,
                "name": info.get("name", "Unknown"),
                "abbr": info.get("abbr", ""),
                "votes": votes,
                "percentage": f"{percentage:.2f}%"
            })
    else:
        # Sort candidates by votes
        sorted_candidates = sorted(agg.candidate_totals.items(), key=lambda x: x[1], reverse=True)
        for position, votes in sorted_candidates[:5]:  # Top 5 candidates
            info = agg.candidate_info.get(position, {})
            percentage = (votes / agg.valid_votes_total * 100) if agg.valid_votes_total > 0 else 0
            agg.winners.append({
                "position": position,
                "name": info.get("name", "Unknown"),
                "party": info.get("party_abbr", ""),
                "votes": votes,
                "percentage": f"{percentage:.2f}%"
            })
    
    # Calculate turnout rate (if we have expected total units)
    if agg.total_polling_units > 0:
        agg.turnout_rate = (agg.polling_units_reporting / agg.total_polling_units) * 100
    
    # Track source ballots
    agg.source_ballots = [b.source_file for b in ballots]
    agg.form_types = list(set(b.form_type for b in ballots))
    
    return agg


def analyze_constituency_discrepancies(agg: AggregatedResults, ballots: list[BallotData], official_data: Optional[dict] = None) -> dict:
    """
    Analyze discrepancies at the constituency level.
    
    Args:
        agg: AggregatedResults with aggregated votes
        ballots: List of source BallotData objects
        official_data: Optional official results for comparison
        
    Returns:
        Dictionary with discrepancy analysis
    """
    analysis = {
        "constituency": f"{agg.province} - {agg.constituency}",
        "overall_discrepancy_rate": agg.discrepancy_rate,
        "ballots_analyzed": len(ballots),
        "problematic_ballots": [],
        "candidate_variance": {},
        "party_variance": {},
        "recommendations": []
    }
    
    # Analyze each ballot's contribution
    is_party_list = bool(agg.party_totals)
    
    if is_party_list:
        # Party-list analysis
        for ballot in ballots:
            if ballot.confidence_score < 0.9:
                analysis["problematic_ballots"].append({
                    "source": ballot.source_file,
                    "confidence": ballot.confidence_score,
                    "issues": ballot.confidence_details
                })
    else:
        # Constituency analysis
        for ballot in ballots:
            if ballot.confidence_score < 0.9:
                analysis["problematic_ballots"].append({
                    "source": ballot.source_file,
                    "confidence": ballot.confidence_score,
                    "issues": ballot.confidence_details
                })
    
    # Calculate variance by candidate/party if official data available
    if official_data:
        if is_party_list:
            official_parties = official_data.get("party_votes", {})
            for party_num_str, agg_votes in agg.party_totals.items():
                official_votes = official_parties.get(int(party_num_str), 0)
                if official_votes > 0:
                    variance_pct = abs(agg_votes - official_votes) / official_votes * 100
                    severity = "HIGH" if variance_pct > 10 else "MEDIUM" if variance_pct > 5 else "LOW"
                    
                    analysis["party_variance"][party_num_str] = {
                        "extracted": agg_votes,
                        "official": official_votes,
                        "variance_pct": f"{variance_pct:.2f}%",
                        "severity": severity
                    }
        else:
            official_candidates = official_data.get("vote_counts", {})
            for position, agg_votes in agg.candidate_totals.items():
                official_votes = official_candidates.get(position, 0)
                if official_votes > 0:
                    variance_pct = abs(agg_votes - official_votes) / official_votes * 100
                    severity = "HIGH" if variance_pct > 10 else "MEDIUM" if variance_pct > 5 else "LOW"
                    
                    analysis["candidate_variance"][position] = {
                        "extracted": agg_votes,
                        "official": official_votes,
                        "variance_pct": f"{variance_pct:.2f}%",
                        "severity": severity
                    }
    
    # Generate recommendations
    if agg.discrepancy_rate > 0.5:
        analysis["recommendations"].append("⚠ CRITICAL: Over 50% of ballots have discrepancies. Recommend manual review of all ballots.")
    elif agg.discrepancy_rate > 0.25:
        analysis["recommendations"].append("⚠ HIGH: 25-50% of ballots have discrepancies. Recommend review of problematic ballots.")
    elif agg.discrepancy_rate > 0.1:
        analysis["recommendations"].append("⚠ MEDIUM: 10-25% of ballots have minor discrepancies. Recommend spot checks.")
    else:
        analysis["recommendations"].append("✓ LOW: <10% discrepancies. Data quality acceptable.")
    
    if agg.aggregated_confidence < 0.85:
        analysis["recommendations"].append("⚠ Low confidence aggregate. Consider re-extraction.")
    else:
        analysis["recommendations"].append("✓ Good confidence aggregate.")
    
    return analysis


def generate_discrepancy_summary(analyses: list[dict]) -> str:
    """
    Generate a summary report of discrepancies across constituencies.
    
    Args:
        analyses: List of discrepancy analysis dicts from analyze_constituency_discrepancies()
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    lines = []
    lines.append("# Discrepancy Analysis Summary")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Overall statistics
    total_constituencies = len(analyses)
    high_discrepancy = sum(1 for a in analyses if a["overall_discrepancy_rate"] > 0.5)
    medium_discrepancy = sum(1 for a in analyses if 0.25 < a["overall_discrepancy_rate"] <= 0.5)
    low_discrepancy = sum(1 for a in analyses if 0 < a["overall_discrepancy_rate"] <= 0.25)
    no_discrepancy = sum(1 for a in analyses if a["overall_discrepancy_rate"] == 0)
    
    lines.append("## Overall Statistics")
    lines.append("")
    lines.append("| Category | Count | Percentage |")
    lines.append("|----------|-------|-----------|")
    lines.append(f"| Constituencies Analyzed | {total_constituencies} | 100% |")
    lines.append(f"| No Discrepancies | {no_discrepancy} | {no_discrepancy/total_constituencies*100:.1f}% |")
    lines.append(f"| Low Discrepancies | {low_discrepancy} | {low_discrepancy/total_constituencies*100:.1f}% |")
    lines.append(f"| Medium Discrepancies | {medium_discrepancy} | {medium_discrepancy/total_constituencies*100:.1f}% |")
    lines.append(f"| High Discrepancies | {high_discrepancy} | {high_discrepancy/total_constituencies*100:.1f}% |")
    lines.append("")
    
    # Problem areas
    problem_areas = [a for a in analyses if a["overall_discrepancy_rate"] > 0.1]
    if problem_areas:
        lines.append("## Problem Areas")
        lines.append("")
        lines.append(f"> ⚠ **{len(problem_areas)} constituency/ies with >10% discrepancies**")
        lines.append("")
        
        for analysis in sorted(problem_areas, key=lambda x: x["overall_discrepancy_rate"], reverse=True):
            rate = analysis["overall_discrepancy_rate"] * 100
            lines.append(f"### {analysis['constituency']}")
            lines.append(f"**Discrepancy Rate:** {rate:.1f}% ({analysis['ballots_analyzed']} ballots analyzed)")
            
            if analysis["problematic_ballots"]:
                lines.append(f"**Problematic Ballots:** {len(analysis['problematic_ballots'])}")
                for ballot in analysis["problematic_ballots"][:3]:
                    lines.append(f"- {ballot['source']}: {ballot['confidence']:.0%} confidence")
            
            lines.append("")
    
    # Recommendations
    lines.append("## Overall Recommendations")
    lines.append("")
    if high_discrepancy > 0:
        lines.append("⚠ **IMMEDIATE ACTION REQUIRED**")
        lines.append(f"- {high_discrepancy} constituency/ies have >50% discrepancies")
        lines.append("- Recommend manual verification of all ballots in these areas")
    elif medium_discrepancy > 0:
        lines.append("⚠ **REVIEW RECOMMENDED**")
        lines.append(f"- {medium_discrepancy} constituency/ies have 25-50% discrepancies")
        lines.append("- Review problematic ballots and re-extract if needed")
    elif low_discrepancy > 0:
        lines.append("✓ **SPOT CHECKS RECOMMENDED**")
        lines.append(f"- {low_discrepancy} constituency/ies have 10-25% discrepancies")
        lines.append("- Minor issues detected, spot checks recommended")
    else:
        lines.append("✓ **NO ACTION NEEDED**")
        lines.append("- All constituencies have acceptable discrepancy rates")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    return "\n".join(lines)


def calculate_vote_statistics(agg: AggregatedResults) -> dict:
    """
    Calculate statistical metrics for aggregated votes.
    
    Args:
        agg: AggregatedResults object
        
    Returns:
        Dictionary with statistics
    """
    import statistics
    
    stats = {
        "vote_distribution": {},
        "outliers": [],
        "anomalies": [],
        "recommendations": []
    }
    
    is_party_list = bool(agg.party_totals)
    votes_list = list(agg.party_totals.values()) if is_party_list else list(agg.candidate_totals.values())
    
    if not votes_list or len(votes_list) < 2:
        return stats
    
    # Calculate basic statistics
    mean_votes = statistics.mean(votes_list)
    median_votes = statistics.median(votes_list)
    stdev_votes = statistics.stdev(votes_list) if len(votes_list) > 1 else 0
    
    stats["vote_distribution"] = {
        "mean": round(mean_votes, 2),
        "median": median_votes,
        "std_dev": round(stdev_votes, 2),
        "min": min(votes_list),
        "max": max(votes_list),
        "range": max(votes_list) - min(votes_list)
    }
    
    # Detect outliers using IQR method
    if len(votes_list) >= 4:
        sorted_votes = sorted(votes_list)
        q1_idx = len(sorted_votes) // 4
        q3_idx = (3 * len(sorted_votes)) // 4
        q1 = sorted_votes[q1_idx]
        q3 = sorted_votes[q3_idx]
        iqr = q3 - q1
        
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        if is_party_list:
            for party_num_str, votes in agg.party_totals.items():
                if votes < lower_bound or votes > upper_bound:
                    info = agg.party_info.get(party_num_str, {})
                    stats["outliers"].append({
                        "party_number": party_num_str,
                        "party_name": info.get("name", "Unknown"),
                        "votes": votes,
                        "type": "LOW" if votes < lower_bound else "HIGH",
                        "severity": "MEDIUM"
                    })
        else:
            for position, votes in agg.candidate_totals.items():
                if votes < lower_bound or votes > upper_bound:
                    info = agg.candidate_info.get(position, {})
                    stats["outliers"].append({
                        "position": position,
                        "candidate_name": info.get("name", "Unknown"),
                        "votes": votes,
                        "type": "LOW" if votes < lower_bound else "HIGH",
                        "severity": "MEDIUM"
                    })
    
    # Detect anomalies (unusual patterns)
    if agg.valid_votes_total > 0:
        if is_party_list:
            for party_num_str, votes in agg.party_totals.items():
                vote_pct = (votes / agg.valid_votes_total) * 100
                
                # Anomaly: One party gets >80% of votes
                if vote_pct > 80:
                    info = agg.party_info.get(party_num_str, {})
                    stats["anomalies"].append({
                        "type": "EXTREME_CONCENTRATION",
                        "party_number": party_num_str,
                        "party_name": info.get("name", "Unknown"),
                        "percentage": f"{vote_pct:.1f}%",
                        "severity": "HIGH",
                        "description": f"Party {party_num_str} received {vote_pct:.1f}% of votes"
                    })
                
                # Anomaly: Zero votes (could indicate missing data or no support)
                if votes == 0 and len(agg.party_totals) > 10:
                    info = agg.party_info.get(party_num_str, {})
                    stats["anomalies"].append({
                        "type": "ZERO_VOTES",
                        "party_number": party_num_str,
                        "party_name": info.get("name", "Unknown"),
                        "votes": 0,
                        "severity": "LOW",
                        "description": f"Party {party_num_str} received zero votes"
                    })
        else:
            for position, votes in agg.candidate_totals.items():
                vote_pct = (votes / agg.valid_votes_total) * 100
                
                # Anomaly: One candidate gets >75% of votes
                if vote_pct > 75:
                    info = agg.candidate_info.get(position, {})
                    stats["anomalies"].append({
                        "type": "EXTREME_CONCENTRATION",
                        "position": position,
                        "candidate_name": info.get("name", "Unknown"),
                        "percentage": f"{vote_pct:.1f}%",
                        "severity": "MEDIUM",
                        "description": f"Position {position} received {vote_pct:.1f}% of votes"
                    })
    
    # Generate recommendations based on statistics
    if stats["outliers"]:
        stats["recommendations"].append(f"⚠ {len(stats['outliers'])} outlier(s) detected. Recommend spot checks.")
    
    if any(a["severity"] == "HIGH" for a in stats["anomalies"]):
        stats["recommendations"].append("⚠ High-severity anomalies detected. Manual review recommended.")
    
    if stdev_votes > mean_votes * 0.5:
        stats["recommendations"].append("⚠ High variance in vote distribution. Verify data consistency.")
    
    if not stats["recommendations"]:
        stats["recommendations"].append("✓ Vote distribution looks normal. No anomalies detected.")
    
    return stats


def detect_anomalous_constituencies(results: dict[tuple, AggregatedResults]) -> list[dict]:
    """
    Identify constituencies with statistical anomalies.
    
    Args:
        results: Dictionary of (province, cons_no) -> AggregatedResults
        
    Returns:
        List of anomaly reports
    """
    anomalies = []
    
    for key, agg in results.items():
        stats = calculate_vote_statistics(agg)
        
        # Check for issues
        if stats["outliers"] or stats["anomalies"] or any("High" in rec or "high" in rec for rec in stats["recommendations"]):
            anomalies.append({
                "constituency": f"{agg.province} - {agg.constituency}",
                "statistics": stats,
                "severity": max(
                    (a.get("severity", "LOW") for a in stats["anomalies"]), 
                    default="LOW"
                ),
                "issue_count": len(stats["outliers"]) + len(stats["anomalies"])
            })
    
    return sorted(anomalies, key=lambda x: x["issue_count"], reverse=True)


def generate_anomaly_report(anomalies: list[dict]) -> str:
    """
    Generate a report of detected anomalies.
    
    Args:
        anomalies: List of anomaly dicts from detect_anomalous_constituencies()
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    lines = []
    lines.append("# Statistical Anomaly Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    if not anomalies:
        lines.append("## No Anomalies Detected")
        lines.append("")
        lines.append("✓ All constituencies show normal statistical patterns.")
        lines.append("")
        return "\n".join(lines)
    
    lines.append("## Summary")
    lines.append("")
    lines.append(f"**Constituencies with Anomalies:** {len(anomalies)}")
    lines.append("")
    
    # Severity breakdown
    high_severity = sum(1 for a in anomalies if a["severity"] == "HIGH")
    medium_severity = sum(1 for a in anomalies if a["severity"] == "MEDIUM")
    low_severity = sum(1 for a in anomalies if a["severity"] == "LOW")
    
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| HIGH | {high_severity} |")
    lines.append(f"| MEDIUM | {medium_severity} |")
    lines.append(f"| LOW | {low_severity} |")
    lines.append("")
    
    # Detailed anomalies
    lines.append("## Detailed Anomalies")
    lines.append("")
    
    for anomaly in anomalies:
        lines.append(f"### {anomaly['constituency']}")
        lines.append(f"**Severity:** {anomaly['severity']} ({anomaly['issue_count']} issues)")
        lines.append("")
        
        stats = anomaly["statistics"]
        
        # Vote distribution stats
        if stats["vote_distribution"]:
            dist = stats["vote_distribution"]
            lines.append("**Vote Distribution:**")
            lines.append(f"- Mean: {dist['mean']} votes")
            lines.append(f"- Median: {dist['median']} votes")
            lines.append(f"- Std Dev: {dist['std_dev']}")
            lines.append(f"- Range: {dist['min']} - {dist['max']} ({dist['range']} spread)")
            lines.append("")
        
        # Outliers
        if stats["outliers"]:
            lines.append("**Outliers Detected:**")
            for outlier in stats["outliers"]:
                if "party_number" in outlier:
                    lines.append(f"- Party #{outlier['party_number']}: {outlier['votes']} votes ({outlier['type']})")
                else:
                    lines.append(f"- Position {outlier['position']}: {outlier['votes']} votes ({outlier['type']})")
            lines.append("")
        
        # Anomalies
        if stats["anomalies"]:
            lines.append("**Pattern Anomalies:**")
            for anomaly_item in stats["anomalies"]:
                lines.append(f"- [{anomaly_item['severity']}] {anomaly_item['description']}")
            lines.append("")
        
        # Recommendations
        if stats["recommendations"]:
            lines.append("**Recommendations:**")
            for rec in stats["recommendations"]:
                lines.append(f"- {rec}")
            lines.append("")
    
    # Footer
    lines.append("---")
    lines.append("")
    lines.append("## Next Steps")
    lines.append("")
    if high_severity > 0:
        lines.append("⚠ **IMMEDIATE ACTION REQUIRED**")
        lines.append(f"- {high_severity} constituency/ies with HIGH severity anomalies")
        lines.append("- Recommend manual verification of these areas")
    elif medium_severity > 0:
        lines.append("⚠ **REVIEW RECOMMENDED**")
        lines.append(f"- {medium_severity} constituency/ies with MEDIUM severity anomalies")
        lines.append("- Verify vote data and polling station reports")
    else:
        lines.append("✓ **ROUTINE CHECKS SUFFICIENT**")
        lines.append("- Low severity anomalies detected")
        lines.append("- Standard verification procedures recommended")
    
    lines.append("")
    
    return "\n".join(lines)


