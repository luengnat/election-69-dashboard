#!/usr/bin/env python3
"""
Visualize OCR results side-by-side with the original image.
Useful for ground truth verification.
"""

import sys
import os
from PIL import Image, ImageDraw, ImageFont
from ballot_extraction import extract_ballot_data_with_ai
from ballot_types import BallotData

def create_side_by_side(image_path: str, output_path: str):
    """
    Generate a side-by-side comparison image.
    Left: Original Image
    Right: Extracted Data
    """
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return

    print(f"Processing {image_path}...")
    data = extract_ballot_data_with_ai(image_path)
    
    if not data:
        print("Extraction failed.")
        return

    # Load original image
    img = Image.open(image_path).convert("RGB")
    
    # Create text canvas
    # Width = 600px, Height = match image
    text_width = 800
    canvas = Image.new("RGB", (text_width, img.height), (250, 250, 250))
    draw = ImageDraw.Draw(canvas)
    
    # Try to load a font (unicode compatible)
    try:
        # MacOS supplemental path for Arial Unicode
        font_path = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
        font = ImageFont.truetype(font_path, 40)
        font_bold = ImageFont.truetype(font_path, 50)
        font_small = ImageFont.truetype(font_path, 30)
    except:
        try:
            # Fallback to standard Helvetica if Unicode font missing
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
            font_bold = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 50)
            font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30)
        except:
            font = ImageFont.load_default()
            font_bold = font
            font_small = font

    # Draw Text
    y = 50
    margin = 40
    
    # Title
    draw.text((margin, y), "OCR Extraction Result", font=font_bold, fill=(0, 0, 0))
    y += 100
    
    # Metadata
    meta_color = (0, 0, 100)
    draw.text((margin, y), f"Form: {data.form_type}", font=font, fill=meta_color)
    y += 60
    draw.text((margin, y), f"Province: {data.province}", font=font, fill=meta_color)
    y += 60
    draw.text((margin, y), f"Constituency: {data.constituency_number}", font=font, fill=meta_color)
    y += 60
    draw.text((margin, y), f"Station: {data.polling_station_id}", font=font, fill=meta_color)
    y += 100
    
    # Vote Table
    draw.text((margin, y), "Vote Counts:", font=font_bold, fill=(0, 0, 0))
    y += 70
    
    # Header
    draw.text((margin, y), "No.   |   Votes", font=font_small, fill=(100, 100, 100))
    y += 50
    draw.line([(margin, y), (text_width - margin, y)], fill=(200, 200, 200), width=2)
    y += 20
    
    # Rows
    votes = data.vote_counts if data.form_category == "constituency" else data.party_votes
    if votes:
        sorted_votes = sorted(votes.items(), key=lambda x: int(x[0]))
        
        for num, count in sorted_votes:
            draw.text((margin, y), f"{num:<5} |   {count}", font=font, fill=(0, 0, 0))
            y += 60
    else:
        draw.text((margin, y), "[No votes detected]", font=font, fill=(200, 0, 0))
        y += 60
        
    y += 40
    draw.line([(margin, y), (text_width - margin, y)], fill=(0, 0, 0), width=3)
    y += 40
    
    # Total
    draw.text((margin, y), f"TOTAL: {data.total_votes}", font=font_bold, fill=(0, 100, 0))
    
    # Confidence
    y += 100
    conf_color = (0, 150, 0) if data.confidence_score > 0.8 else (200, 0, 0)
    draw.text((margin, y), f"Confidence: {data.confidence_score:.1%}", font=font_small, fill=conf_color)

    # Combine
    combined_width = img.width + text_width
    combined = Image.new("RGB", (combined_width, img.height))
    combined.paste(img, (0, 0))
    combined.paste(canvas, (img.width, 0))
    
    combined.save(output_path)
    print(f"Saved visualization to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python visualize_ocr.py <image_path> <output_path>")
    else:
        create_side_by_side(sys.argv[1], sys.argv[2])
