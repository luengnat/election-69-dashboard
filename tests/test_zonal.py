from segmentation_utils import detect_dotted_lines, extract_zonal_snippets
import os

target = "test_images/page-1.png"
if os.path.exists(target):
    print(f"Detecting dotted lines in {target}...")
    lines = detect_dotted_lines(target)
    print(f"Found {len(lines)} lines.")
    
    for i, line in enumerate(lines[:5]):
        print(f"Line {i}: {line}")
        
    print(f"\nExtracting snippets...")
    snippets = extract_zonal_snippets(target, "test_snippets")
    print(f"Generated {len(snippets)} snippets in test_snippets/")
    
    if len(snippets) > 0:
        print("Success: Zonal extraction logic is functional.")
    else:
        print("Fail: No snippets generated.")
else:
    print("Test image not found.")

