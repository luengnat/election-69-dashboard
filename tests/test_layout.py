from layout_verifier import verifier
import os

test_image = "test_images/page-1.png"
if os.path.exists(test_image):
    print(f"Testing layout verification on {test_image}...")
    result = verifier.verify(test_image)
    if result:
        print(f"Result: {result}")
        if result.is_ballot:
            print("SUCCESS: Identified as ballot")
        else:
            print("FAIL: Not identified as ballot")
    else:
        print("SKIPPED: VLM not available or failed")
else:
    print("Test image not found")
