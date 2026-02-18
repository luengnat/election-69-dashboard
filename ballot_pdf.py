#!/usr/bin/env python3
"""
PDF report generation for ballot data.

Contains: markdown_table_to_pdf_table, generate_ballot_pdf,
_create_confidence_chart, _create_province_pie_chart,
_create_votes_bar_chart, generate_batch_pdf, generate_constituency_pdf,
generate_executive_summary_pdf, _create_compact_stats_table,
_format_discrepancy_summary_inline, _create_top_parties_chart,
generate_one_page_executive_summary_pdf.
"""

from typing import Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from batch_processor import BatchResult

from ballot_types import BallotData, AggregatedResults

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.graphics.charts.barcharts import VerticalBarChart, HorizontalBarChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics import renderPDF
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

def markdown_table_to_pdf_table(markdown_table: str) -> tuple[list, list]:
    """
    Convert markdown table to PDF table format.
    
    Args:
        markdown_table: Markdown table string with | separators
        
    Returns:
        (data_rows, table_style) for reportlab Table
    """
    lines = [line.strip() for line in markdown_table.strip().split('\n') if line.strip()]
    if len(lines) < 2:
        return [], []
    
    # Parse header
    header = [cell.strip() for cell in lines[0].split('|')[1:-1]]
    
    # Skip separator line
    data_rows = [header]
    
    # Parse data rows
    for line in lines[2:]:
        if not line.strip():
            continue
        cells = [cell.strip() for cell in line.split('|')[1:-1]]
        if cells:
            data_rows.append(cells)
    
    # Create table style
    table_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E0E0E0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
    ]
    
    return data_rows, table_style


def generate_ballot_pdf(ballot_data: BallotData, output_path: str) -> bool:
    """
    Generate a professional PDF report for a single ballot.
    
    Args:
        ballot_data: Extracted ballot data
        output_path: Path to save PDF
        
    Returns:
        True if successful, False otherwise
    """
    if not HAS_REPORTLAB:
        print("✗ reportlab not installed. Install with: pip install reportlab")
        return False
    
    try:
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=12,
            alignment=TA_CENTER,
        )
        story.append(Paragraph("Ballot Verification Report", title_style))
        story.append(Spacer(1, 0.2*inch))
        
        # Form Information Section
        story.append(Paragraph("Form Information", styles['Heading2']))
        
        form_data = [
            ['Field', 'Value'],
            ['Form Type', ballot_data.form_type],
            ['Category', ballot_data.form_category.title()],
            ['Province', ballot_data.province],
            ['Constituency', str(ballot_data.constituency_number)],
            ['District', ballot_data.district or 'N/A'],
            ['Polling Unit', str(ballot_data.polling_unit)],
            ['Polling Station', ballot_data.polling_station_id or 'N/A'],
            ['Source File', ballot_data.source_file],
        ]
        
        form_table = Table(form_data, colWidths=[2*inch, 4*inch])
        form_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
        ]))
        story.append(form_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Vote Summary Section
        story.append(Paragraph("Vote Summary", styles['Heading2']))
        
        vote_data = [
            ['Metric', 'Count'],
            ['Valid Votes', str(ballot_data.valid_votes)],
            ['Invalid Votes', str(ballot_data.invalid_votes)],
            ['Blank Votes', str(ballot_data.blank_votes)],
            ['Total Votes', f"<b>{ballot_data.total_votes}</b>"],
        ]
        
        vote_table = Table(vote_data, colWidths=[3*inch, 3*inch])
        vote_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#E8F0F8')),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(vote_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Quality Assessment
        story.append(Paragraph("Extraction Quality", styles['Heading2']))
        
        confidence_pct = int(ballot_data.confidence_score * 100)
        confidence_level = ballot_data.confidence_details.get('level', 'UNKNOWN')
        
        quality_color = {
            'EXCELLENT': colors.HexColor('#2ecc71'),
            'GOOD': colors.HexColor('#3498db'),
            'ACCEPTABLE': colors.HexColor('#f39c12'),
            'POOR': colors.HexColor('#e74c3c'),
        }.get(confidence_level, colors.grey)
        
        quality_text = f"<font color='{quality_color.hexval()}' size=12><b>✓ {confidence_level}</b></font> ({confidence_pct}%)"
        story.append(Paragraph(quality_text, styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        # Candidate votes (if applicable)
        if ballot_data.form_category == 'constituency' and ballot_data.candidate_info:
            story.append(Paragraph("Candidate Votes", styles['Heading2']))
            
            cand_data = [['Position', 'Candidate Name', 'Party', 'Votes']]
            for pos, info in sorted(ballot_data.candidate_info.items()):
                votes = ballot_data.vote_counts.get(int(pos), 0)
                party = info.get('party_abbr', '?')
                cand_data.append([str(pos), info['name'], party, str(votes)])
            
            cand_table = Table(cand_data, colWidths=[1*inch, 2.5*inch, 1.2*inch, 1.3*inch])
            cand_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (1, 1), (1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ]))
            story.append(cand_table)
            story.append(Spacer(1, 0.3*inch))
        
        # Party votes (if applicable)
        elif ballot_data.form_category == 'party_list' and ballot_data.party_votes:
            story.append(Paragraph("Party Votes", styles['Heading2']))
            
            party_data = [['Party', 'Votes', 'Percentage']]
            total_pv = sum(ballot_data.party_votes.values())
            for party_no, votes in sorted(ballot_data.party_votes.items()):
                pct = (votes / total_pv * 100) if total_pv > 0 else 0
                party_data.append([str(party_no), str(votes), f"{pct:.1f}%"])
            
            party_table = Table(party_data, colWidths=[2*inch, 2*inch, 2*inch])
            party_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ]))
            story.append(party_table)
            story.append(Spacer(1, 0.3*inch))
        
        # Footer
        story.append(Spacer(1, 0.3*inch))
        footer_text = f"<i>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        story.append(Paragraph(footer_text, styles['Normal']))
        
        doc.build(story)
        print(f"✓ PDF report saved to: {output_path}")
        return True

    except Exception as e:
        print(f"✗ Error generating PDF: {e}")
        return False


def _create_confidence_chart(ballot_data_list: list) -> "Drawing":
    """Create a bar chart showing confidence level distribution."""
    # Count by confidence level
    levels = {"EXCELLENT": 0, "GOOD": 0, "ACCEPTABLE": 0, "POOR": 0, "VERY_LOW": 0}
    for ballot in ballot_data_list:
        level = ballot.confidence_details.get("level", "POOR")
        if level in levels:
            levels[level] += 1
        else:
            levels["POOR"] += 1

    drawing = Drawing(400, 200)

    bc = VerticalBarChart()
    bc.x = 50
    bc.y = 50
    bc.height = 125
    bc.width = 300
    bc.data = [[levels["EXCELLENT"], levels["GOOD"], levels["ACCEPTABLE"], levels["POOR"], levels["VERY_LOW"]]]
    bc.strokeColor = colors.black
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max(levels.values()) + 1 if max(levels.values()) > 0 else 5
    bc.valueAxis.valueStep = 1
    bc.categoryAxis.labels.boxAnchor = 'ne'
    bc.categoryAxis.labels.dx = 8
    bc.categoryAxis.labels.dy = -2
    bc.categoryAxis.labels.angle = 30
    bc.categoryAxis.categoryNames = ['Excellent', 'Good', 'Acceptable', 'Poor', 'Very Low']

    # Color the bars
    bc.bars[0].fillColor = colors.HexColor('#1f4788')

    drawing.add(bc)

    # Title
    title = String(200, 180, 'Confidence Distribution', fontSize=12, fillColor=colors.black, textAnchor='middle')
    drawing.add(title)

    return drawing


def _create_province_pie_chart(ballot_data_list: list) -> "Drawing":
    """Create a pie chart showing ballot distribution by province."""
    # Count by province
    provinces = {}
    for ballot in ballot_data_list:
        prov = ballot.province or "Unknown"
        provinces[prov] = provinces.get(prov, 0) + 1

    # Sort and take top 8, group rest as "Other"
    sorted_provs = sorted(provinces.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_provs) > 8:
        top_provs = sorted_provs[:8]
        other_count = sum(c for _, c in sorted_provs[8:])
        if other_count > 0:
            top_provs.append(("Other", other_count))
    else:
        top_provs = sorted_provs

    drawing = Drawing(400, 250)

    pie = Pie()
    pie.x = 100
    pie.y = 50
    pie.width = 150
    pie.height = 150
    pie.data = [c for _, c in top_provs]
    pie.labels = [p[:15] for p, _ in top_provs]  # Truncate long names

    # Colors for pie slices
    pie_colors = [
        colors.HexColor('#1f4788'),
        colors.HexColor('#3498db'),
        colors.HexColor('#2ecc71'),
        colors.HexColor('#f39c12'),
        colors.HexColor('#e74c3c'),
        colors.HexColor('#9b59b6'),
        colors.HexColor('#1abc9c'),
        colors.HexColor('#34495e'),
        colors.HexColor('#95a5a6'),
    ]
    for i in range(len(top_provs)):
        pie.slices[i].fillColor = pie_colors[i % len(pie_colors)]

    pie.slices.strokeWidth = 0.5

    drawing.add(pie)

    # Title
    title = String(200, 220, 'Ballots by Province', fontSize=12, fillColor=colors.black, textAnchor='middle')
    drawing.add(title)

    return drawing


def _create_votes_bar_chart(aggregated_results: dict) -> "Drawing":
    """Create a bar chart showing total votes by constituency."""
    if not aggregated_results:
        return None

    # Get vote totals per constituency
    constituencies = []
    for (province, cons_no), agg in aggregated_results.items():
        cons_name = f"{province[:10]}-{cons_no}"
        constituencies.append((cons_name, agg.valid_votes_total))

    # Sort by votes and take top 10
    constituencies.sort(key=lambda x: x[1], reverse=True)
    top_cons = constituencies[:10]

    if not top_cons:
        return None

    drawing = Drawing(450, 220)

    bc = VerticalBarChart()
    bc.x = 50
    bc.y = 50
    bc.height = 125
    bc.width = 350
    bc.data = [[v for _, v in top_cons]]
    bc.strokeColor = colors.black
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max(v for _, v in top_cons) + 50
    bc.categoryAxis.labels.boxAnchor = 'ne'
    bc.categoryAxis.labels.dx = 8
    bc.categoryAxis.labels.dy = -2
    bc.categoryAxis.labels.angle = 45
    bc.categoryAxis.labels.fontSize = 7
    bc.categoryAxis.categoryNames = [name for name, _ in top_cons]

    bc.bars[0].fillColor = colors.HexColor('#2ecc71')

    drawing.add(bc)

    # Title
    title = String(225, 195, 'Valid Votes by Constituency (Top 10)', fontSize=11, fillColor=colors.black, textAnchor='middle')
    drawing.add(title)

    return drawing


def generate_batch_pdf(aggregated_results: dict, ballot_data_list: list, output_path: str) -> bool:
    """
    Generate a PDF batch summary report.
    
    Args:
        aggregated_results: Dictionary of aggregated results by constituency
        ballot_data_list: List of all BallotData objects
        output_path: Path to save PDF
        
    Returns:
        True if successful, False otherwise
    """
    if not HAS_REPORTLAB:
        print("✗ reportlab not installed. Install with: pip install reportlab")
        return False
    
    try:
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=12,
            alignment=TA_CENTER,
        )
        story.append(Paragraph("Batch Ballot Verification Report", title_style))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Overall Statistics
        story.append(Paragraph("Overall Statistics", styles['Heading2']))
        
        total_ballots = len(ballot_data_list)
        verified_count = len([b for b in ballot_data_list if b.confidence_score >= 0.90])
        
        stats_data = [
            ['Metric', 'Count', 'Percentage'],
            ['Total Ballots', str(total_ballots), '100%'],
            ['Verified (High Confidence)', str(verified_count), f"{verified_count/total_ballots*100:.1f}%"],
        ]
        
        stats_table = Table(stats_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Form Type Breakdown
        story.append(Paragraph("Form Type Breakdown", styles['Heading2']))
        
        form_types = {}
        for ballot in ballot_data_list:
            form_types[ballot.form_type] = form_types.get(ballot.form_type, 0) + 1
        
        form_data = [['Form Type', 'Count']]
        for form_type, count in sorted(form_types.items()):
            form_data.append([form_type, str(count)])
        
        form_table = Table(form_data, colWidths=[3*inch, 3*inch])
        form_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(form_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Province Breakdown
        story.append(Paragraph("Province Breakdown", styles['Heading2']))
        
        provinces = {}
        for ballot in ballot_data_list:
            provinces[ballot.province] = provinces.get(ballot.province, 0) + 1
        
        prov_data = [['Province', 'Count']]
        for province, count in sorted(provinces.items()):
            prov_data.append([province, str(count)])
        
        prov_table = Table(prov_data, colWidths=[3*inch, 3*inch])
        prov_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(prov_table)
        story.append(Spacer(1, 0.3*inch))

        # Charts Section
        story.append(PageBreak())
        story.append(Paragraph("Visual Analysis", styles['Heading2']))
        story.append(Spacer(1, 0.2*inch))

        # Confidence Distribution Chart
        if len(ballot_data_list) > 0:
            story.append(Paragraph("Confidence Level Distribution", styles['Heading3']))
            conf_chart = _create_confidence_chart(ballot_data_list)
            story.append(conf_chart)
            story.append(Spacer(1, 0.3*inch))

        # Province Pie Chart
        if len(ballot_data_list) > 1:
            story.append(Paragraph("Ballot Distribution by Province", styles['Heading3']))
            prov_chart = _create_province_pie_chart(ballot_data_list)
            story.append(prov_chart)
            story.append(Spacer(1, 0.3*inch))

        # Votes by Constituency Chart (if aggregated data available)
        if aggregated_results:
            story.append(Paragraph("Valid Votes by Constituency", styles['Heading3']))
            votes_chart = _create_votes_bar_chart(aggregated_results)
            if votes_chart:
                story.append(votes_chart)
            story.append(Spacer(1, 0.3*inch))

        # Ballot Details (per page if many)
        if len(ballot_data_list) > 0 and len(ballot_data_list) <= 10:
            story.append(PageBreak())
            story.append(Paragraph("Ballot Details", styles['Heading2']))
            
            ballot_data = [['#', 'Form Type', 'Province', 'Station', 'Valid Votes', 'Confidence']]
            for i, ballot in enumerate(ballot_data_list, 1):
                confidence_level = ballot.confidence_details.get('level', 'UNKNOWN')
                ballot_data.append([
                    str(i),
                    ballot.form_type,
                    ballot.province,
                    ballot.polling_station_id or 'N/A',
                    str(ballot.valid_votes),
                    confidence_level
                ])
            
            ballot_table = Table(ballot_data, colWidths=[0.5*inch, 1.2*inch, 1*inch, 1.5*inch, 1*inch, 1.2*inch])
            ballot_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ]))
            story.append(ballot_table)
        
        doc.build(story)
        print(f"✓ Batch PDF report saved to: {output_path}")
        return True
        
    except Exception as e:
        print(f"✗ Error generating batch PDF: {e}")
        return False


def generate_constituency_pdf(agg: "AggregatedResults", output_path: str) -> bool:
    """
    Generate a professional PDF report for aggregated constituency results.

    Args:
        agg: AggregatedResults object with aggregated data
        output_path: Path to save PDF

    Returns:
        True if successful, False otherwise
    """
    if not HAS_REPORTLAB:
        print("✗ reportlab not installed. Install with: pip install reportlab")
        return False

    try:
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=12,
            alignment=TA_CENTER,
        )
        story.append(Paragraph("Constituency Results Report", title_style))
        story.append(Spacer(1, 0.2*inch))

        # Constituency Information Section
        story.append(Paragraph("Constituency Information", styles['Heading2']))

        info_data = [
            ['Field', 'Value'],
            ['Province', agg.province],
            ['Constituency', agg.constituency],
            ['Constituency #', str(agg.constituency_no)],
        ]

        info_table = Table(info_data, colWidths=[2*inch, 4*inch])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 0.3*inch))

        # Data Collection Status
        story.append(Paragraph("Data Collection Status", styles['Heading2']))

        status_data = [
            ['Metric', 'Value'],
            ['Ballots Processed', str(agg.ballots_processed)],
            ['Polling Units Reporting', str(agg.polling_units_reporting)],
            ['Reporting Rate', f"{float(agg.turnout_rate or 0):.1f}%"],
            ['Form Types Used', ', '.join(agg.form_types) if agg.form_types else 'N/A'],
        ]

        status_table = Table(status_data, colWidths=[3*inch, 3*inch])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
        ]))
        story.append(status_table)
        story.append(Spacer(1, 0.3*inch))

        # Vote Totals
        story.append(Paragraph("Vote Totals", styles['Heading2']))

        vote_data = [
            ['Category', 'Votes'],
            ['Valid Votes', str(agg.valid_votes_total)],
            ['Invalid Votes', str(agg.invalid_votes_total)],
            ['Blank Votes', str(agg.blank_votes_total)],
            ['Overall Total', f"<b>{agg.overall_total}</b>"],
        ]

        vote_table = Table(vote_data, colWidths=[3*inch, 3*inch])
        vote_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#E8F0F8')),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(vote_table)
        story.append(Spacer(1, 0.3*inch))

        # Quality Assessment
        story.append(Paragraph("Data Quality", styles['Heading2']))

        confidence_pct = int(agg.aggregated_confidence * 100)
        if agg.aggregated_confidence >= 0.95:
            confidence_level = 'EXCELLENT'
            quality_color = colors.HexColor('#2ecc71')
        elif agg.aggregated_confidence >= 0.85:
            confidence_level = 'GOOD'
            quality_color = colors.HexColor('#3498db')
        elif agg.aggregated_confidence >= 0.70:
            confidence_level = 'ACCEPTABLE'
            quality_color = colors.HexColor('#f39c12')
        else:
            confidence_level = 'POOR'
            quality_color = colors.HexColor('#e74c3c')

        quality_text = f"<font color='{quality_color.hexval()}' size=12><b>✓ {confidence_level}</b></font> ({confidence_pct}%)"
        story.append(Paragraph(quality_text, styles['Normal']))
        story.append(Paragraph(f"Discrepancy Rate: {float(agg.discrepancy_rate or 0):.1%}", styles['Normal']))
        story.append(Paragraph(f"Ballots with Issues: {agg.ballots_with_discrepancies}/{agg.ballots_processed}", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))

        # Results table - determine if party-list or constituency
        is_party_list = bool(agg.party_totals)

        if is_party_list:
            story.append(Paragraph("Party Results", styles['Heading2']))

            party_data = [['Party #', 'Party Name', 'Abbr', 'Votes', 'Percentage']]
            sorted_results = sorted(agg.party_totals.items(), key=lambda x: x[1], reverse=True)

            for party_num_str, votes in sorted_results:
                info = agg.party_info.get(party_num_str, {})
                party_name = info.get("name", "Unknown")
                abbr = info.get("abbr", "")
                votes_int = int(votes) if votes else 0
                percentage = (votes_int / agg.valid_votes_total * 100) if agg.valid_votes_total > 0 else 0
                party_data.append([str(party_num_str), party_name[:25], abbr, str(votes_int), f"{percentage:.2f}%"])

            if len(party_data) > 1:
                party_table = Table(party_data, colWidths=[0.8*inch, 2.5*inch, 0.8*inch, 1*inch, 1*inch])
                party_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('ALIGN', (1, 1), (1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
                ]))
                story.append(party_table)
        else:
            story.append(Paragraph("Candidate Results", styles['Heading2']))

            cand_data = [['Pos', 'Candidate Name', 'Party', 'Votes', 'Percentage']]
            sorted_results = sorted(agg.candidate_totals.items(), key=lambda x: x[1], reverse=True)

            for position, votes in sorted_results:
                info = agg.candidate_info.get(position, {})
                candidate_name = info.get("name", "Unknown")
                party = info.get("party_abbr", "")
                votes_int = int(votes) if votes else 0
                percentage = (votes_int / agg.valid_votes_total * 100) if agg.valid_votes_total > 0 else 0
                cand_data.append([str(position), candidate_name[:30], party, str(votes_int), f"{percentage:.2f}%"])

            if len(cand_data) > 1:
                cand_table = Table(cand_data, colWidths=[0.6*inch, 2.8*inch, 0.8*inch, 1*inch, 1*inch])
                cand_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('ALIGN', (1, 1), (1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
                ]))
                story.append(cand_table)

        story.append(Spacer(1, 0.3*inch))

        # Winners section
        if agg.winners:
            story.append(Paragraph("Top Results", styles['Heading2']))

            for i, winner in enumerate(agg.winners[:3], 1):
                if is_party_list:
                    winner_text = f"<b>#{i}</b> {winner.get('name', 'N/A')} ({winner.get('abbr', '')})"
                else:
                    winner_text = f"<b>#{i}</b> {winner.get('name', 'N/A')} ({winner.get('party', '')})"
                pct_val = winner.get('percentage', 0)
                if isinstance(pct_val, str):
                    pct_val = float(pct_val.rstrip('%'))
                else:
                    pct_val = float(pct_val or 0)
                votes_text = f"Votes: {winner.get('votes', 0)} ({pct_val:.2f}%)"
                story.append(Paragraph(winner_text, styles['Normal']))
                story.append(Paragraph(f"    {votes_text}", styles['Normal']))

            story.append(Spacer(1, 0.2*inch))

        # Source Information
        if agg.source_ballots:
            story.append(Paragraph("Source Information", styles['Heading2']))
            for source in agg.source_ballots[:10]:  # Limit to 10 sources
                story.append(Paragraph(f"• {source}", styles['Normal']))
            if len(agg.source_ballots) > 10:
                story.append(Paragraph(f"<i>... and {len(agg.source_ballots) - 10} more</i>", styles['Normal']))

        # Footer
        story.append(Spacer(1, 0.3*inch))
        footer_text = f"<i>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        story.append(Paragraph(footer_text, styles['Normal']))

        doc.build(story)
        print(f"✓ Constituency PDF report saved to: {output_path}")
        return True

    except Exception as e:
        print(f"✗ Error generating constituency PDF: {e}")
        return False


def generate_executive_summary_pdf(
    all_results: list["AggregatedResults"],
    anomalies: list[dict],
    output_path: str,
    provinces: Optional[list[str]] = None
) -> bool:
    """
    Generate a professional PDF executive summary report.

    Args:
        all_results: All AggregatedResults from all constituencies
        anomalies: All detected anomalies
        output_path: Path to save PDF
        provinces: Optional list of provinces (auto-detected if None)

    Returns:
        True if successful, False otherwise
    """
    if not HAS_REPORTLAB:
        print("✗ reportlab not installed. Install with: pip install reportlab")
        return False

    if not all_results:
        print("✗ No results to summarize")
        return False

    try:
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Detect provinces if not provided
        if provinces is None:
            provinces = sorted(set(r.province for r in all_results))

        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=20,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=12,
            alignment=TA_CENTER,
        )
        story.append(Paragraph("Electoral Results", title_style))
        story.append(Paragraph("Executive Summary", styles['Heading2']))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))

        # Key Statistics
        total_valid = sum(r.valid_votes_total for r in all_results)
        total_invalid = sum(r.invalid_votes_total for r in all_results)
        total_blank = sum(r.blank_votes_total for r in all_results)
        total_votes = sum(r.overall_total for r in all_results)
        avg_confidence = (sum(r.aggregated_confidence for r in all_results) / len(all_results)) if all_results else 0

        story.append(Paragraph("Key Statistics", styles['Heading2']))

        stats_data = [
            ['Metric', 'Value'],
            ['Total Constituencies', str(len(all_results))],
            ['Total Provinces', str(len(provinces))],
            ['Total Valid Votes', f"{total_valid:,}"],
            ['Total Invalid Votes', f"{total_invalid:,}"],
            ['Total Blank Votes', f"{total_blank:,}"],
            ['Overall Total', f"<b>{total_votes:,}</b>"],
            ['Average Confidence', f"{avg_confidence:.1%}"],
        ]

        stats_table = Table(stats_data, colWidths=[3*inch, 3*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 6), (-1, 6), colors.HexColor('#E8F0F8')),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 0.3*inch))

        # Data Quality Assessment
        story.append(Paragraph("Data Quality Assessment", styles['Heading2']))

        if avg_confidence >= 0.95:
            quality_rating = "EXCELLENT"
            quality_color = colors.HexColor('#2ecc71')
        elif avg_confidence >= 0.85:
            quality_rating = "GOOD"
            quality_color = colors.HexColor('#3498db')
        elif avg_confidence >= 0.75:
            quality_rating = "ACCEPTABLE"
            quality_color = colors.HexColor('#f39c12')
        else:
            quality_rating = "POOR"
            quality_color = colors.HexColor('#e74c3c')

        quality_text = f"<font color='{quality_color.hexval()}' size=14><b>{quality_rating}</b></font>"
        story.append(Paragraph(f"Overall Rating: {quality_text}", styles['Normal']))
        story.append(Paragraph(f"Average Confidence: {avg_confidence:.1%}", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))

        # Province Summary
        story.append(Paragraph("Results by Province", styles['Heading2']))

        prov_data = [['Province', 'Constituencies', 'Valid Votes', 'Avg Confidence']]
        for province in provinces:
            prov_results = [r for r in all_results if r.province == province]
            if prov_results:
                prov_valid = sum(r.valid_votes_total for r in prov_results)
                prov_conf = sum(r.aggregated_confidence for r in prov_results) / len(prov_results)
                prov_data.append([province, str(len(prov_results)), f"{prov_valid:,}", f"{prov_conf:.1%}"])

        if len(prov_data) > 1:
            prov_table = Table(prov_data, colWidths=[2*inch, 1.5*inch, 1.5*inch, 1.5*inch])
            prov_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ]))
            story.append(prov_table)
            story.append(Spacer(1, 0.3*inch))

        # Top Candidates (if constituency results)
        is_party_list = bool(all_results[0].party_totals) if all_results else False
        if not is_party_list:
            story.append(Paragraph("Top Candidates Overall", styles['Heading2']))

            # Aggregate all candidates
            all_winners = []
            for result in all_results:
                for winner in result.winners:
                    all_winners.append({
                        "name": winner["name"],
                        "province": result.province,
                        "votes": winner.get("votes", 0),
                        "percentage": winner.get("percentage", 0)
                    })

            # Sort by votes
            top_winners = sorted(all_winners, key=lambda x: x["votes"] if isinstance(x["votes"], int) else 0, reverse=True)[:10]

            if top_winners:
                cand_data = [['Rank', 'Candidate', 'Province', 'Votes', '%']]
                for i, winner in enumerate(top_winners, 1):
                    pct_val = winner["percentage"]
                    if isinstance(pct_val, str):
                        pct_val = pct_val.rstrip('%')
                    cand_data.append([
                        str(i),
                        winner["name"][:25],
                        winner["province"][:15],
                        str(winner["votes"]),
                        f"{float(pct_val or 0):.1f}%"
                    ])

                cand_table = Table(cand_data, colWidths=[0.5*inch, 2.5*inch, 1.2*inch, 1*inch, 0.8*inch])
                cand_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('ALIGN', (1, 1), (1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
                ]))
                story.append(cand_table)
                story.append(Spacer(1, 0.3*inch))

        # Issues & Recommendations
        story.append(PageBreak())
        story.append(Paragraph("Issues & Recommendations", styles['Heading2']))

        if anomalies:
            high_anomalies = [a for a in anomalies if a.get("severity") == "HIGH"]
            medium_anomalies = [a for a in anomalies if a.get("severity") == "MEDIUM"]

            story.append(Paragraph(f"<b>Total Anomalies Detected:</b> {len(anomalies)}", styles['Normal']))
            story.append(Spacer(1, 0.1*inch))

            if high_anomalies:
                story.append(Paragraph(f"<font color='#e74c3c'><b>CRITICAL ({len(high_anomalies)}):</b></font>", styles['Normal']))
                for anom in high_anomalies[:5]:
                    story.append(Paragraph(f"  • {anom.get('constituency', 'Unknown')}", styles['Normal']))
                story.append(Spacer(1, 0.1*inch))

            if medium_anomalies:
                story.append(Paragraph(f"<font color='#f39c12'><b>NEEDS REVIEW ({len(medium_anomalies)}):</b></font>", styles['Normal']))
                for anom in medium_anomalies[:5]:
                    story.append(Paragraph(f"  • {anom.get('constituency', 'Unknown')}", styles['Normal']))
                story.append(Spacer(1, 0.2*inch))
        else:
            story.append(Paragraph("✓ No anomalies detected", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))

        # Final Recommendations
        story.append(Paragraph("Recommendations", styles['Heading3']))
        if avg_confidence < 0.85:
            story.append(Paragraph("⚠ <b>Low average confidence.</b> Consider re-verification of data.", styles['Normal']))
        elif anomalies and len(anomalies) > len(all_results) * 0.2:
            story.append(Paragraph("⚠ <b>High anomaly rate.</b> Manual review of flagged constituencies recommended.", styles['Normal']))
        else:
            story.append(Paragraph("✓ <b>Data quality acceptable.</b> Proceed with standard verification process.", styles['Normal']))

        # Footer
        story.append(Spacer(1, 0.5*inch))
        footer_text = "<i>Report generated automatically by Thai Election Ballot OCR</i>"
        story.append(Paragraph(footer_text, styles['Normal']))

        doc.build(story)
        print(f"✓ Executive Summary PDF saved to: {output_path}")
        return True

    except Exception as e:
        print(f"✗ Error generating executive summary PDF: {e}")
        return False


# =============================================================================
# One-Page Executive Summary PDF Generation (Phase 8)
# =============================================================================

def _create_compact_stats_table(all_results: list["AggregatedResults"], ballots_processed: int, duration_seconds: float) -> "Table":
    """
    Create a compact 2-column stats table for one-page executive summary.

    Args:
        all_results: List of AggregatedResults
        ballots_processed: Total number of ballots processed
        duration_seconds: Processing duration in seconds

    Returns:
        Formatted Table with compact stats
    """
    if not all_results:
        # Empty state
        stats_data = [
            ['Total Ballots', '0', 'Total Provinces', '0'],
            ['Valid Votes', '0', 'Avg Confidence', '0%'],
            ['Invalid Votes', '0', 'Processing Time', '0.0s'],
        ]
    else:
        total_valid = sum(r.valid_votes_total for r in all_results)
        total_invalid = sum(r.invalid_votes_total for r in all_results)
        avg_confidence = sum(r.aggregated_confidence for r in all_results) / len(all_results)
        provinces = len(set(r.province for r in all_results))

        stats_data = [
            ['Total Ballots', str(ballots_processed), 'Total Provinces', str(provinces)],
            ['Valid Votes', f"{total_valid:,}", 'Avg Confidence', f"{avg_confidence:.1%}"],
            ['Invalid Votes', f"{total_invalid:,}", 'Processing Time', f"{duration_seconds:.1f}s"],
        ]

    table = Table(stats_data, colWidths=[1.3*inch, 1.2*inch, 1.3*inch, 1.2*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f0f0f0')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
    ]))
    return table


def _format_discrepancy_summary_inline(all_results: list["AggregatedResults"]) -> "Paragraph":
    """
    Format discrepancy summary as inline color-coded text.

    Args:
        all_results: List of AggregatedResults with discrepancy_rate field

    Returns:
        Paragraph with color-coded discrepancy counts
    """
    if not all_results:
        text = (
            "<font color='#2ecc71'><b>NONE: 0</b></font>"
        )
    else:
        # Count by severity
        critical = sum(1 for r in all_results if r.discrepancy_rate > 0.5)
        medium = sum(1 for r in all_results if 0.25 < r.discrepancy_rate <= 0.5)
        low = sum(1 for r in all_results if 0 < r.discrepancy_rate <= 0.25)
        none = sum(1 for r in all_results if r.discrepancy_rate == 0)

        # Color-coded inline format
        text = (
            f"<font color='#e74c3c'><b>CRITICAL: {critical}</b></font> | "
            f"<font color='#f39c12'><b>MEDIUM: {medium}</b></font> | "
            f"<font color='#3498db'><b>LOW: {low}</b></font> | "
            f"<font color='#2ecc71'><b>NONE: {none}</b></font>"
        )

    return Paragraph(f"Discrepancy Summary: {text}", ParagraphStyle(
        'DiscrepancyStyle',
        fontSize=9,
        spaceAfter=6,
        spaceBefore=6
    ))


def _create_top_parties_chart(all_results: list["AggregatedResults"], width: float = None, height: float = None) -> "Drawing":
    """
    Create a compact horizontal bar chart for top 5 parties by total votes.

    Args:
        all_results: List of AggregatedResults with party_totals
        width: Chart width (default 5 inches)
        height: Chart height (default 2 inches)

    Returns:
        Drawing with horizontal bar chart, or None if no party data
    """
    if not HAS_REPORTLAB:
        return None

    # Set defaults after HAS_REPORTLAB check so inch is defined
    if width is None:
        width = 5*inch
    if height is None:
        height = 2*inch

    # Aggregate all party votes
    party_totals = {}
    for result in all_results:
        for party_num, votes in result.party_totals.items():
            party_totals[party_num] = party_totals.get(party_num, 0) + votes

    # Sort and take top 5
    sorted_parties = sorted(party_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    if not sorted_parties:
        return None

    drawing = Drawing(width, height)

    bc = HorizontalBarChart()
    bc.x = 80  # Space for labels
    bc.y = 20
    bc.height = height - 40
    bc.width = width - 100
    bc.data = [[v for _, v in sorted_parties]]
    bc.strokeColor = colors.black
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max(v for _, v in sorted_parties) * 1.1
    bc.categoryAxis.categoryNames = [f"Party {p}" for p, _ in sorted_parties]
    bc.bars[0].fillColor = colors.HexColor('#1f4788')

    drawing.add(bc)

    # Title
    title = String(width / 2, height - 10, 'Top 5 Parties by Total Votes', fontSize=10, fillColor=colors.black, textAnchor='middle')
    drawing.add(title)

    return drawing


def generate_one_page_executive_summary_pdf(
    all_results: list["AggregatedResults"],
    batch_result: "BatchResult",
    output_path: str
) -> bool:
    """
    Generate a one-page executive summary PDF with key batch statistics.

    This function creates a compact, single-page PDF summary with:
    - Compact 2-column stats table
    - Color-coded discrepancy summary by severity
    - Top 5 parties horizontal bar chart
    - Batch metadata footer

    Args:
        all_results: List of AggregatedResults from all constituencies
        batch_result: BatchResult with timing and metadata
        output_path: Path to save PDF

    Returns:
        True if successful, False otherwise
    """
    if not HAS_REPORTLAB:
        print("reportlab not installed. Install with: pip install reportlab")
        return False

    if not all_results:
        print("No results to summarize")
        return False

    try:
        # Document setup with tight margins for one-page layout
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=0.5*inch,
            rightMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        styles = getSampleStyleSheet()
        story = []

        # Title (compact, 14pt)
        title_style = ParagraphStyle(
            'CompactTitle',
            parent=styles['Heading1'],
            fontSize=14,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=6,
            alignment=TA_CENTER,
        )
        story.append(Paragraph("Electoral Results - Executive Summary", title_style))

        # Timestamp line
        timestamp_style = ParagraphStyle(
            'Timestamp',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER,
            spaceAfter=8
        )
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", timestamp_style))

        # Small spacer
        story.append(Spacer(1, 0.1*inch))

        # Compact stats table
        stats_table = _create_compact_stats_table(
            all_results,
            batch_result.processed if hasattr(batch_result, 'processed') else len(all_results),
            batch_result.duration_seconds if hasattr(batch_result, 'duration_seconds') else 0.0
        )
        story.append(stats_table)

        # Small spacer
        story.append(Spacer(1, 0.1*inch))

        # Discrepancy summary (inline, color-coded)
        discrepancy_para = _format_discrepancy_summary_inline(all_results)
        story.append(discrepancy_para)

        # Small spacer
        story.append(Spacer(1, 0.1*inch))

        # Top 5 parties horizontal bar chart
        chart = _create_top_parties_chart(all_results)
        if chart:
            story.append(chart)
        else:
            # Fallback message if no party data
            no_chart_style = ParagraphStyle(
                'NoChart',
                parent=styles['Normal'],
                fontSize=9,
                textColor=colors.grey,
                alignment=TA_CENTER
            )
            story.append(Paragraph("(No party-list data available)", no_chart_style))

        # Small spacer
        story.append(Spacer(1, 0.1*inch))

        # Footer with batch metadata (smaller font, 7pt italic)
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=7,
            textColor=colors.grey,
            alignment=TA_CENTER,
            fontName='Helvetica-Oblique'
        )
        processed_count = batch_result.processed if hasattr(batch_result, 'processed') else len(all_results)
        duration = batch_result.duration_seconds if hasattr(batch_result, 'duration_seconds') else 0.0
        footer_text = f"Batch processed: {processed_count} ballots in {duration:.1f}s"
        story.append(Paragraph(footer_text, footer_style))

        # Build the PDF (NO PageBreak() - single page constraint)
        doc.build(story)
        print(f"One-page Executive Summary PDF saved to: {output_path}")
        return True

    except Exception as e:
        print(f"Error generating one-page executive summary PDF: {e}")
        return False


