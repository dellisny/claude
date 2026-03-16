#!/usr/bin/env bash
# Daily sync — commit all changes and push to GitHub
set -e

cd "$(dirname "$0")"

if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    echo "Nothing to commit."
    exit 0
fi

echo ""
echo "About to:"
echo "  1. git add -A"
echo "  2. git commit -m \"Daily sync $(date '+%Y-%m-%d')\""
echo "  3. git push origin main"
echo ""
read -r -p "Proceed? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

git add -A
git commit -m "Daily sync $(date '+%Y-%m-%d')"
git push origin main
echo "Done."
