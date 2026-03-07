# PR Review Bot

Automated GitHub PR reviewer using Ollama (llama3.2). Runs every 3 hours, posts inline
review comments based on project-specific guide files — no code suggestions, comments only.

## How It Works

```
Every 3 hours (cron)
    ↓
List open PRs via GitHub API
    ↓
For each PR:
  ├── Already commented + all resolved? → APPROVE
  ├── Already commented + unresolved?   → SKIP (wait for dev)
  └── No bot comment yet?               → REVIEW
          ↓
    Classify PR (test / code / mixed / frontend)
          ↓
    Load guide file(s) from guides/
          ↓
    Fetch diff via GitHub API
          ↓
    Split large diffs into chunks (>8000 chars)
          ↓
    Send each chunk to Ollama llama3.2
    Prompt = guide + diff → structured JSON response
          ↓
    Merge comments, max 8 per PR
          ↓
    Post REQUEST_CHANGES or APPROVE via GitHub API
```

## Setup

### 1. Install Ollama and pull llama3.2

```bash
# Install Ollama (https://ollama.com)
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model
ollama pull llama3.2
```

### 2. Install Python dependency

```bash
pip install requests
```

### 3. Set environment variables

Create `/etc/pr-review-bot.env` (or add to your shell profile):

```bash
export GITHUB_TOKEN=ghp_your_personal_access_token
export GITHUB_REPO=Orenda-Project/taleemabad-core
export BOT_USERNAME=oyekamal          # GitHub username that posts reviews
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=llama3.2
export GUIDES_DIR=/absolute/path/to/.github/pr-review-bot/guides
```

GitHub token needs scopes: `repo` (read + write PRs and reviews).

### 4. Set up cron job

```bash
crontab -e
```

Add this line (runs every 3 hours):

```cron
0 */3 * * * source /etc/pr-review-bot.env && python3 /path/to/.github/scripts/pr_review_bot.py >> /var/log/pr_review_bot.log 2>&1
```

### 5. Test manually

```bash
source /etc/pr-review-bot.env
python3 .github/scripts/pr_review_bot.py
```

## Guide Files

| File | Used for |
|------|----------|
| `guides/TEST_REVIEW_GUIDE.md` | PRs where >50% changed Python files are in `*/tests/*` |
| `guides/CODE_REVIEW_GUIDE.md` | PRs with non-test Python/Django code changes |

Both guides are loaded for mixed PRs (test + code changes).

## Review Logic

- **REQUEST_CHANGES**: violations found → inline comments on offending lines
- **APPROVE**: previously reviewed PR where all threads are now resolved
- **COMMENT**: neutral feedback (e.g. frontend PRs not yet automated)
- Comments are short (1-2 sentences, no code) — purely guidance

## Adding a New Guide

1. Create `guides/YOUR_GUIDE.md` following the same format as existing guides
2. Update the `classify_pr()` function in `pr_review_bot.py` to use it
3. End the guide with the exact `## OUTPUT FORMAT` section so the LLM knows the JSON schema

## Logs

```bash
tail -f /var/log/pr_review_bot.log
```
