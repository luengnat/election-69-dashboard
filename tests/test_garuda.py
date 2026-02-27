from segmentation_utils import detect_garuda
import os

target = "test_images/page-1.png"
if os.path.exists(target):
    print(f"Detecting Garuda in {target}...")
    coords = detect_garuda(target)
    if coords:
        print(f"Found Garuda at: {coords}")
        print("Success: Advanced segmentation (Form Separation) is feasible.")
    else:
        print("Garuda not found.")
else:
    print("Test image not found.")
