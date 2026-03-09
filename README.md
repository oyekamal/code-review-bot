# PR Review Bot

An automated GitHub PR review bot powered by Claude AI. It reviews pull requests, posts inline code comments, requests changes when issues are found, and approves PRs when the code looks clean — all without manual intervention.

## What It Does

- **Reviews open PRs automatically** — fetches the diff, sends each changed file to Claude, and posts inline review comments directly on GitHub
- **Backend-only focus** — skips JS/TS/CSS/frontend files; only reviews Python/Django backend code
- **Smart guide routing** — uses `TEST_REVIEW_GUIDE.md` for test files, `CODE_REVIEW_GUIDE.md` for everything else
- **Approves or requests changes** — posts `APPROVE` if the code is clean, `REQUEST_CHANGES` if issues are found
- **Deduplication** — skips re-posting comments that already exist on the same line (within 5 lines)
- **SHA-based skip** — tracks every reviewed PR in `.bot/reviews.json`; if the HEAD commit hasn't changed since the last run, the PR is skipped entirely (no LLM call, no GitHub write)
- **Skips your own PRs** — will not review PRs authored by the authenticated GitHub user
- **Branch filter** — only reviews PRs targeting a configured branch (default: `develop`)

## Setup

### 1. Install

```bash
pip install -r requirements.txt
pip install -e .
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in:
# GITHUB_TOKEN=ghp_...
# ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Configure your project

Edit `config/projects.yaml`:

```yaml
projects:
  - name: my-project
    repo: org/repo-name
    github_token_env: GITHUB_TOKEN
    llm:
      provider: anthropic
      model: claude-haiku-4-5-20251001
      api_key_env: ANTHROPIC_API_KEY
    discovery:
      auto_detect: false
      frameworks:
        - django
      guide_files:
        - path/to/CODE_REVIEW_GUIDE.md
        - path/to/TEST_REVIEW_GUIDE.md
    review:
      max_comments: 8
      auto_approve_on_resolution: false
      target_branch: develop
```

## Usage

```bash
# Review all open PRs (skips unchanged ones automatically)
pr-review-bot review --project my-project

# Review a specific PR
pr-review-bot review --project my-project --pr 123

# Dry run — generate review but don't post to GitHub
pr-review-bot review --project my-project --pr 123 --dry-run

# List open PRs
pr-review-bot list-prs --project my-project

# List configured projects
pr-review-bot list-projects
```

## How the Review Works

1. Fetches all open PRs targeting the configured `target_branch`
2. Skips PRs authored by the bot account
3. Skips PRs whose HEAD SHA matches the last recorded review in `.bot/reviews.json`
4. For each remaining PR, fetches the unified diff
5. Filters to backend files only (skips `.js`, `.ts`, `.jsx`, `.tsx`, `.css`, etc.)
6. Sends each file's diff to Claude with the appropriate review guide as context
7. Validates LLM-suggested comment line numbers against the actual diff (adjusts by up to 10 lines if needed)
8. Deduplicates against existing bot comments on the PR
9. Posts the review: inline comments + summary + `APPROVE` or `REQUEST_CHANGES`
10. Records the result in `.bot/reviews.json`

## LLM Providers

**Anthropic Claude (recommended)**
```yaml
llm:
  provider: anthropic
  model: claude-haiku-4-5-20251001
  api_key_env: ANTHROPIC_API_KEY
```

**Ollama (local, free)**
```yaml
llm:
  provider: ollama
  model: llama3.2
  base_url: http://localhost:11434
```

## Adding Another Project

Add a new entry to `config/projects.yaml`:

```yaml
  - name: another-project
    repo: org/another-repo
    github_token_env: GITHUB_TOKEN
    llm:
      provider: anthropic
      model: claude-haiku-4-5-20251001
      api_key_env: ANTHROPIC_API_KEY
    review:
      target_branch: main
```

## Automating with Cron

To run every 2 hours on your machine:

```bash
crontab -e
# Add:
0 */2 * * * cd /path/to/code-review-bot && source .venv/bin/activate && pr-review-bot review --project my-project >> logs/cron.log 2>&1
```

## Logs

```bash
# Stream logs in real time
tail -f logs/pr_review_bot.log | jq .
```

## Environment Variables

| Variable | Description |
|---|---|
| `GITHUB_TOKEN` | GitHub personal access token with `repo` scope |
| `ANTHROPIC_API_KEY` | Claude API key (if using anthropic provider) |
| `OLLAMA_BASE_URL` | Ollama server URL (default: `http://localhost:11434`) |
| `LOG_LEVEL` | Logging level (default: `INFO`) |
