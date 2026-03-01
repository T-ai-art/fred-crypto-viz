#!/bin/bash
# Setup script for GitHub Pages deployment
# Prerequisites: gh CLI installed and authenticated (brew install gh && gh auth login)

set -e

REPO_NAME="crypto-data-explorer"

echo "=== Creating GitHub repository: $REPO_NAME ==="

# Initialize git
git init
git add .
git commit -m "Initial commit: FRED-style crypto data explorer"

# Create remote repo
gh repo create "$REPO_NAME" --public --source=. --push

echo ""
echo "=== Next Steps ==="
echo "1. Go to: https://github.com/$(gh api user -q .login)/$REPO_NAME/settings/pages"
echo "2. Source: 'GitHub Actions'"
echo "3. Run: Actions tab → 'Update Crypto Data' → 'Run workflow'"
echo ""
echo "Your site will be at: https://$(gh api user -q .login).github.io/$REPO_NAME/"
