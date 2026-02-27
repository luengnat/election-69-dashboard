from cv_helpers import deskew_image, extract_vote_cells
import sys

image_path = "/Users/nat/dev/election/test_images/page-1.png"
if len(sys.argv) > 1:
    image_path = sys.argv[1]

deskewed_path = deskew_image(image_path)
print(f"Deskewed image saved to: {deskewed_path}")

cell_paths = extract_vote_cells(deskewed_path)
print(f"Extracted {len(cell_paths)} cells.")
for p in cell_paths[:5]:
    print(f" - {p}")
