#!/usr/bin/env bash
# Daily sync — commit all changes and push to GitHub
set -e

cd "$(dirname "$0")"

if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    echo "Nothing to commit."
    exit 0
fi

git add -A
git commit -m "Daily sync $(date '+%Y-%m-%d')"
git push origin main
echo "Done."
