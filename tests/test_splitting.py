from segmentation_utils import split_pages_by_landmark
import os

# Simulate a merged PDF sequence: Page 1, Page 2, Page 1 (New unit)
# We'll use page-1.png as the landmark source
pages = [
    "test_images/page-1.png",
    "test_images/page-2.png",
    "test_images/page-1.png" # Simulated start of unit 2
]

if all(os.path.exists(p) for p in pages):
    print("Testing multi-form splitting...")
    units = split_pages_by_landmark(pages)
    
    print(f"Found {len(units)} units.")
    for i, unit in enumerate(units):
        print(f"Unit {i+1}: {len(unit)} pages")
        
    if len(units) == 2:
        print("Success: Correctly split into 2 units.")
    else:
        print("Fail: Did not split correctly.")
else:
    print("Test images not found.")
