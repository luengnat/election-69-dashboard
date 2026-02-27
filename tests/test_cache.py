from ocr_cache import cache
from ballot_types import BallotData
import os

# Create dummy ballot data
data = BallotData(
    form_type="Test",
    form_category="TestCat",
    province="TestProv",
    source_file="test_cache.txt"
)

# Create dummy file
with open("test_cache.txt", "w") as f:
    f.write("test content")

# Test Set
print("Setting cache...")
cache.set("test_cache.txt", data)

# Test Get
print("Getting cache...")
cached_data = cache.get("test_cache.txt")

if cached_data:
    print(f"Retrieved: {cached_data.province}")
    if cached_data.province == "TestProv":
        print("SUCCESS")
    else:
        print("FAIL: Content mismatch")
else:
    print("FAIL: Not found")

# Cleanup
os.remove("test_cache.txt")
