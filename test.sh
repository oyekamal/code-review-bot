#!/usr/bin/env bash
# Quick setup and test script

set -e

echo "🚀 PR Review Bot - Quick Test"
echo "=============================="
echo ""

# Set GitHub token
export GITHUB_TOKEN=$(gh auth token)
echo "✓ GitHub token configured"

# Test CLI
echo "✓ Testing CLI..."
/home/oye/Documents/code-review-bot/.venv/bin/pr-review-bot list-projects > /dev/null
echo "✓ CLI is working"

# Check Ollama
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✓ Ollama is running"
else
    echo "⚠ Ollama is not running - please run: ollama serve"
    exit 1
fi

echo ""
echo "🧪 Testing PR #4677 (dry run)..."
echo ""

# Run test (dry run)
/home/oye/Documents/code-review-bot/.venv/bin/pr-review-bot test-llm --project taleemabad-core --pr 4677

echo ""
echo "✅ Test completed!"
echo ""
echo "Next steps:"
echo "  1. Review the output above"
echo "  2. To post the review: pr-review-bot review --project taleemabad-core --pr 4677"
echo "  3. To review all open PRs: pr-review-bot review --project taleemabad-core"
