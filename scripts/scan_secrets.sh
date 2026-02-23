#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PATTERN='BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY|AIza[0-9A-Za-z_-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-|hf_[A-Za-z0-9]{20,}'

echo "Scanning tracked files for potential secrets..."
if rg -n --hidden -S "$PATTERN" \
  --glob '!.git/**' \
  --glob '!docs/data/*.geojson' \
  --glob '!*.png' --glob '!*.jpg' --glob '!*.jpeg' --glob '!*.pdf' \
  .; then
  echo
  echo "Potential secret(s) detected. Review and redact before commit."
  exit 1
fi

echo "No known secret patterns detected."

