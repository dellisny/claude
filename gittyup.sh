#!/usr/bin/env bash
# Daily sync — commit all changes and push to GitHub
set -e

cd "$(dirname "$0")"

if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    echo "Nothing to commit."
    exit 0
fi

echo ""
echo "Local changes:"
git status --short | sed 's/^/  /'
echo ""
ahead=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
echo "Remote: will push $((ahead + 1)) commit(s) to origin/main"
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
