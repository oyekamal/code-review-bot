# Workflow: PR Review Bot

## Objective

Automatically review open pull requests in the `taleemabad-core` repo. Call Claude only when truly needed, never post duplicate comments, and track every comment's full lifecycle (posted → replied → resolved) so the bot gets smarter over time.

---

## Inputs Required

| What | Where | Notes |
|---|---|---|
| GitHub token | `.env` → `GITHUB_TOKEN` | Needs `pull_requests:write`, `contents:read` |
| Anthropic API key | `.env` → `ANTHROPIC_API_KEY` | Claude Haiku by default |
| Project config | `config/projects.yaml` | Repo, guide paths, max comments |
| Review guides | `pr-review-bot/guides/` | Loaded from the target repo, not this one |

---

## Tools

| Tool | Script / Command |
|---|---|
| Run all PRs | `pr-review-bot review --project taleemabad-core` |
| Run single PR | `pr-review-bot review --project taleemabad-core --pr <N>` |
| Dry run (no post, no DB write) | `pr-review-bot review --project taleemabad-core --pr <N> --dry-run` |
| Test LLM output only | `pr-review-bot test-llm --project taleemabad-core --pr <N>` |
| List open PRs + status | `pr-review-bot list-prs --project taleemabad-core` |
| View structured logs | `tail -f logs/pr_review_bot.log \| jq .` |

---

## Decision Tree

The bot runs this logic for every open PR targeting `develop`:

```
1. SKIP if PR is authored by the bot account itself

2. SKIP if HEAD SHA matches .bot/reviews.json (no new commits)
   → No LLM call, no GitHub API write

3. If bot's last review was REQUEST_CHANGES:
   a. Query GitHub GraphQL for unresolved bot threads
   b. If 0 unresolved → APPROVE immediately (no LLM call)
   c. If > 0 unresolved → SKIP (don't pile on)
   d. If GraphQL fails (returns -1) → fall through to normal review

4. Normal review (LLM call per file):
   a. Fetch PR diff, split by file
   b. Skip non-Python files (.js, .css, .json, .yaml, etc.)
   c. Skip files with < 50 chars of diff
   d. For each remaining file:
      - Route to TEST_REVIEW_GUIDE or CODE_REVIEW_GUIDE
      - Call Claude with guide + diff
      - Collect comments from JSON response
   e. Deduplicate (see section below)
   f. Cap at max_comments (default: 8)
   g. POST review to GitHub with inline comments

5. Record result to .bot/reviews.json:
   - Summary record (sha, event, counts)
   - Each posted comment individually (path, line, body, status)

6. After every run (SKIP or not):
   - Sync resolution status from GitHub into reviews.json
   - Fetch and store user replies to bot comments
```

---

## Comment Deduplication Logic

The bot uses two-tier deduplication so it never posts the same comment twice:

**Tier 1 — Local DB (fast, no API call):**
- On any PR the bot has reviewed before, `reviews.json` stores every comment it posted (path + line + body)
- Before posting, filter out any new comment where `same path AND |new_line - stored_line| ≤ 20`
- This handles line number drift from new commits in the same PR

**Tier 2 — GitHub API (first run only):**
- If no stored history exists (first time seeing this PR), query GitHub for existing bot comments
- Uses the same 20-line tolerance

**Resolution awareness:**
- When a user resolves a thread, `_sync_comment_statuses()` marks it `"resolved"` in `reviews.json`
- Resolved comments are excluded from the dedup check — this allows the bot to comment again if the *same area* gets modified later

---

## What Gets Stored in `.bot/reviews.json`

```json
{
  "taleemabad-core": {
    "4691": {
      "pr_number": 4691,
      "title": "Add bulk import feature",
      "head_sha": "abc123def456",
      "reviewed_at": "2026-03-12T09:00:00",
      "event": "REQUEST_CHANGES",
      "files_reviewed": 3,
      "comments_posted": 5,
      "comments": [
        {
          "path": "api/views.py",
          "line": 42,
          "body": "This calls .delete() directly — use SoftDeleteAuditableMixin instead.",
          "posted_at": "2026-03-12T09:01:00",
          "status": "unresolved",
          "resolved_at": null,
          "user_reply": "Fixed, switched to is_active=False"
        }
      ]
    }
  }
}
```

**Status lifecycle:** `unresolved` → `resolved` (synced from GitHub GraphQL)

---

## Learning from Comments

Every run calls `_record_user_replies()` which:
1. Fetches all review comments on the PR (bot + developer)
2. Matches developer comments to stored bot comments by `path + line (±5)`
3. Stores the developer's reply text in `reviews.json`

Over time, `reviews.json` becomes a dataset of: what the bot said, what developers replied, and whether threads were resolved. This can be used to tune the review guides or identify patterns in what gets ignored vs. acted on.

---

## Debugging Guide

### Bot posts 0 comments

1. Check which files are in the diff:
   ```bash
   pr-review-bot test-llm --project taleemabad-core --pr <N>
   ```
2. If all files are non-Python (JS/CSS/YAML), `_is_backend_file()` is filtering them out — this is correct behaviour
3. If Python files exist but 0 comments:
   - Check LLM raw output in logs: `tail -f logs/pr_review_bot.log | jq .`
   - If LLM returned `{"comments": []}` → guide may need updating
   - If `file_diff` was < 50 chars → diff too short to review (also correct)

### Bot re-posts a comment it already made

1. Check `reviews.json` for this PR — does the `comments` array have the previous comment?
   ```bash
   cat .bot/reviews.json | jq '.["taleemabad-core"]["<PR_NUMBER>"].comments'
   ```
2. If missing: the comment was posted before this fix was deployed. Run the bot once — it will fall back to the GitHub API for dedup on that run, then populate the DB
3. If present but bot still re-posted: check the `path` and `line` match (±20 tolerance). If paths differ, the LLM may be using a shortened path that doesn't match stored path

### Bot SKIPs a PR that should be reviewed

1. Check why it was skipped:
   ```bash
   tail -f logs/pr_review_bot.log | jq 'select(.msg | contains("skipping"))'
   ```
2. Common causes:
   - `sha=...unchanged` → New commits haven't been pushed yet
   - `unresolved bot thread` → Developer hasn't resolved prior feedback — this is intentional
   - `authored by bot` → PR was created by the bot account itself

### GitHub API / Claude API errors

1. Verify tokens:
   ```bash
   cat .env | grep -E 'GITHUB_TOKEN|ANTHROPIC_API_KEY'
   ```
2. Test Claude independently:
   ```bash
   pr-review-bot test-llm --project taleemabad-core --pr <N>
   ```
3. Check logs for HTTP error codes:
   ```bash
   tail -100 logs/pr_review_bot.log | jq 'select(.level == "error")'
   ```
4. GitHub rate limit: 5000 req/hour for PAT. The bot makes ~3–5 API calls per PR; at 20 open PRs that's ~100 calls — well within limit

### reviews.json gets corrupted or out of sync

1. The file is safe to edit manually — it's plain JSON
2. To force a re-review of a specific PR (ignoring SHA cache):
   ```bash
   # Remove the entry for that PR
   cat .bot/reviews.json | jq 'del(.["taleemabad-core"]["<PR_NUMBER>"])' > /tmp/reviews_tmp.json
   mv /tmp/reviews_tmp.json .bot/reviews.json
   ```
3. To reset entirely: `echo '{}' > .bot/reviews.json`

---

## When to Update This Workflow

Update this file when:
- A new project is added to `config/projects.yaml`
- The review guides change significantly
- A new GitHub API behaviour is discovered (rate limits, auth changes)
- A recurring failure pattern is identified and fixed

Do **not** overwrite this file during a one-off debugging session. Document the fix in the relevant source file and update this workflow only when the fix is verified and stable.

---

## File Map

| Concern | File |
|---|---|
| Main orchestrator | `src/pr_review_bot/core/smart_reviewer.py` |
| GitHub API | `src/pr_review_bot/integrations/github/client.py` |
| Claude API | `src/pr_review_bot/integrations/llm/anthropic.py` |
| Persistent DB | `src/pr_review_bot/core/review_db.py` |
| Diff parsing | `src/pr_review_bot/core/diff_parser.py` |
| Config models | `src/pr_review_bot/config/settings.py` |
| CLI commands | `src/pr_review_bot/cli/commands.py` |
| Project config | `config/projects.yaml` |
| Review DB (data) | `.bot/reviews.json` |
| Logs | `logs/pr_review_bot.log` |
| Backend guide | `pr-review-bot/guides/CODE_REVIEW_GUIDE.md` |
| Test guide | `pr-review-bot/guides/TEST_REVIEW_GUIDE.md` |
