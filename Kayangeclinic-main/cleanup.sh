#!/usr/bin/env bash
# Run from inside Kayangeclinic-main/ (the folder that contains api/ and app/)
set -e
rm -rf api/backup kayange-management-system
mkdir -p _scratch && mv test_*.py check_*.py fix_*.py verify_fix.py _scratch/ 2>/dev/null || true
echo "_scratch/" >> .gitignore
echo "Done. Entrypoint is now api/index.py only (run.py kept for local/Procfile)."
