# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies and package in dev mode
pip install -r requirements.txt
pip install -e .

# Run the CLI
pr-review-bot list-projects
pr-review-bot discover --project taleemabad-core
pr-review-bot list-prs --project taleemabad-core
pr-review-bot review --project taleemabad-core --pr <number> --dry-run
pr-review-bot review --project taleemabad-core --pr <number>
pr-review-bot review --project taleemabad-core   # Review all open PRs
pr-review-bot test-llm --project taleemabad-core --pr <number>

# Quick test script
python test_pr_4677.py

# Run tests
pytest

# View structured logs
tail -f logs/pr_review_bot.log | jq .
```

## Architecture

The bot is a modular Python package (`src/pr_review_bot/`) with four layers:

**`config/`** — Pydantic v2 models loaded from `config/projects.yaml` + `.env`. Key models: `LLMConfig`, `ProjectSettings`, `Settings`. The YAML defines multiple projects, each with its own repo, GitHub token, LLM provider, and guide files.

**`core/`** — Business logic:
- `smart_reviewer.py` — `SmartReviewer` orchestrates the full pipeline: clone repo (if needed) → detect frameworks → load guides → fetch PR diff → call LLM per file → validate comments → post to GitHub. Cached project profiles are stored in `.bot/profiles/{project}.json`.
- `detector.py` — `FrameworkDetector` auto-detects Django, React, Next.js, FastAPI, Flask by checking file patterns and package manifests.
- `guide_loader.py` — Loads markdown guide files from the target repo and concatenates them into a single LLM prompt string.
- `diff_parser.py` — Parses unified diffs into per-file diffs; validates that LLM-suggested comment line numbers exist in the diff (5-line tolerance). Handles path shortening from LLM output.

**`integrations/`** — External services:
- `integrations/llm/base.py` — Abstract `LLMProvider` with `review(guide, diff, pr_context)` and `health_check()`.
- `integrations/llm/ollama.py` — Local Ollama via `/api/generate` (JSON mode, temp 0.3).
- `integrations/llm/anthropic.py` — Claude API (temp 0.3, max 4096 tokens).
- `integrations/github/client.py` — PyGithub wrapper; handles PR fetch, diff retrieval, review posting with inline comments and path matching.

**`cli/commands.py`** — Click CLI; all commands delegate to `SmartReviewer`.

## Review Database

`.bot/reviews.json` — persists every review keyed by project → PR number. Each entry stores `head_sha`, `reviewed_at`, `event`, `files_reviewed`, `comments_posted`. On each run, PRs whose HEAD SHA hasn't changed since the last review are skipped entirely — no LLM call, no GitHub API write.

## Key Design Decisions

- **LLM prompt returns JSON** with `{"comments": [{"path", "line", "body"}]}`. Both providers use the same prompt structure.
- **Per-file LLM calls** — each changed file is sent separately to stay within token limits; `max_comments` in config caps the total.
- **Path matching** — LLM often returns shortened paths; `DiffParser` and `GitHubClient` do fuzzy matching to resolve them.
- **`auto_detect: false`** in the current config means frameworks are manually specified and no repo clone is needed.
- **Guide files** (`pr-review-bot/guides/`) are loaded from the *target* repository (taleemabad-core), not this bot repo.

## Environment Variables

```
GITHUB_TOKEN          # GitHub PAT
ANTHROPIC_API_KEY     # Claude API key (if using anthropic provider)
OLLAMA_BASE_URL       # Default: http://localhost:11434
OLLAMA_MODEL          # Default: llama3.2
LOG_LEVEL             # Default: INFO
```
