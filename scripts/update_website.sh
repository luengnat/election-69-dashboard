#!/bin/bash
#
# update_website.sh - Sync election data to the GitHub Pages website
#
# This script copies the latest data files from the election OCR repo
# to the GitHub Pages website repo for public deployment.
#
# Usage:
#   ./scripts/update_website.sh [website_repo_path]
#
# Arguments:
#   website_repo_path - Path to the website repo (default: /tmp/election-main)
#
# Examples:
#   ./scripts/update_website.sh
#   ./scripts/update_website.sh ~/repos/election-website
#
# What this script does:
#   1. Copies district_dashboard_data.json to website docs/data/
#   2. Copies CSV reports to website root
#   3. Runs export_first2_csv.py to generate constituency/party-list CSVs
#   4. Prints summary of changes
#
# After running this script:
#   cd /tmp/election-main
#   git add -A
#   git commit -m "Update election data"
#   git push
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WEBSITE_REPO="${1:-/tmp/election-main}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Election Website Update Script ===${NC}"
echo ""

# Verify website repo exists
if [ ! -d "$WEBSITE_REPO" ]; then
    echo -e "${RED}Error: Website repo not found at $WEBSITE_REPO${NC}"
    echo "Please clone the website repo first or provide the correct path."
    exit 1
fi

# Verify source data exists
SOURCE_DATA="$REPO_ROOT/docs/data/district_dashboard_data.json"
if [ ! -f "$SOURCE_DATA" ]; then
    echo -e "${RED}Error: Source data not found at $SOURCE_DATA${NC}"
    exit 1
fi

echo -e "${YELLOW}Source repo:${NC} $REPO_ROOT"
echo -e "${YELLOW}Website repo:${NC} $WEBSITE_REPO"
echo ""

# Step 1: Copy district dashboard data
echo -e "${GREEN}Step 1: Copying district dashboard data...${NC}"
cp "$SOURCE_DATA" "$WEBSITE_REPO/docs/data/"
echo "  ✓ docs/data/district_dashboard_data.json"

# Step 2: Copy CSV reports
echo -e "${GREEN}Step 2: Copying CSV reports...${NC}"
if [ -f "$REPO_ROOT/docs/data/recheck_all_partylist_sum_issues.csv" ]; then
    cp "$REPO_ROOT/docs/data/recheck_all_partylist_sum_issues.csv" "$WEBSITE_REPO/"
    echo "  ✓ recheck_all_partylist_sum_issues.csv"
fi

if [ -f "$REPO_ROOT/docs/data/recheck_all_vs_killernay_diffs.csv" ]; then
    cp "$REPO_ROOT/docs/data/recheck_all_vs_killernay_diffs.csv" "$WEBSITE_REPO/"
    echo "  ✓ recheck_all_vs_killernay_diffs.csv"
fi

if [ -f "$REPO_ROOT/docs/data/recheck_all_vs_killernay_summary.json" ]; then
    cp "$REPO_ROOT/docs/data/recheck_all_vs_killernay_summary.json" "$WEBSITE_REPO/"
    echo "  ✓ recheck_all_vs_killernay_summary.json"
fi

# Step 3: Generate export CSVs
echo -e "${GREEN}Step 3: Generating export CSVs...${NC}"
cd "$WEBSITE_REPO"
python3 scripts/export_first2_csv.py \
    --input docs/data/district_dashboard_data.json \
    --out-const export_first2_constituency_100.csv \
    --out-party export_first2_party_list_100.csv

# Step 4: Summary
echo ""
echo -e "${GREEN}=== Update Complete ===${NC}"
echo ""
echo "Files updated in $WEBSITE_REPO:"
echo "  - docs/data/district_dashboard_data.json"
echo "  - export_first2_constituency_100.csv"
echo "  - export_first2_party_list_100.csv"
echo "  - recheck_all_*.csv/json"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  cd $WEBSITE_REPO"
echo "  git add -A"
echo "  git status  # Review changes"
echo "  git commit -m 'Update election data: $(date +%Y-%m-%d)'"
echo "  git push"
