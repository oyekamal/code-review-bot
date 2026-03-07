#!/usr/bin/env python3
"""
PR Review Bot — Automated GitHub PR reviews using Ollama (llama3.2)
Run via cron every 3 hours. See .github/pr-review-bot/README.md for setup.

# Dependencies: pip install requests
# Standard library: os, json, logging, time, pathlib, typing
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "Orenda-Project/taleemabad-core")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "oyekamal")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
GUIDES_DIR = Path(
    os.environ.get(
        "GUIDES_DIR",
        str(Path(__file__).parent.parent / "pr-review-bot" / "guides"),
    )
)
MAX_DIFF_CHARS = 8000
MAX_COMMENTS = 8
GITHUB_API_BASE = "https://api.github.com"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------


def _github_headers() -> dict[str, str]:
    if not GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN is not set — API calls may be rate-limited or fail.")
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_get(path: str, params: Optional[dict] = None, retry: bool = True) -> Any:
    """GET from the GitHub REST API. Returns parsed JSON or raises on failure."""
    url = f"{GITHUB_API_BASE}{path}"
    response = requests.get(url, headers=_github_headers(), params=params, timeout=30)

    if response.status_code == 403 and "rate limit" in response.text.lower():
        if retry:
            log.warning("GitHub rate limit hit. Sleeping 60 s then retrying once.")
            time.sleep(60)
            return _github_get(path, params, retry=False)
        log.warning("GitHub rate limit still hit after retry. Aborting.")
        raise SystemExit(0)

    response.raise_for_status()
    return response.json()


def _github_post(path: str, body: dict, retry: bool = True) -> Any:
    """POST to the GitHub REST API. Returns parsed JSON or raises on failure."""
    url = f"{GITHUB_API_BASE}{path}"
    response = requests.post(
        url, headers=_github_headers(), json=body, timeout=30
    )

    if response.status_code == 403 and "rate limit" in response.text.lower():
        if retry:
            log.warning("GitHub rate limit hit on POST. Sleeping 60 s then retrying once.")
            time.sleep(60)
            return _github_post(path, body, retry=False)
        log.warning("GitHub rate limit still hit after POST retry. Aborting.")
        raise SystemExit(0)

    response.raise_for_status()
    return response.json()


def _github_get_raw(path: str) -> str:
    """GET raw diff content from GitHub API."""
    url = f"{GITHUB_API_BASE}{path}"
    headers = _github_headers()
    headers["Accept"] = "application/vnd.github.v3.diff"
    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()
    return response.text


# ---------------------------------------------------------------------------
# PR listing and metadata
# ---------------------------------------------------------------------------


def list_open_prs() -> list[dict]:
    """Return all open PRs for the configured repo (non-draft by default)."""
    prs: list[dict] = []
    page = 1
    while True:
        batch = _github_get(
            f"/repos/{GITHUB_REPO}/pulls",
            params={"state": "open", "per_page": 100, "page": page},
        )
        if not batch:
            break
        prs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    log.info("Found %d open PRs.", len(prs))
    return prs


def get_pr_labels(pr: dict) -> list[str]:
    return [lbl["name"] for lbl in pr.get("labels", [])]


def get_pr_files(pr_number: int) -> list[dict]:
    """Return file metadata for a PR (filename, status, additions, deletions, etc.)."""
    files: list[dict] = []
    page = 1
    while True:
        batch = _github_get(
            f"/repos/{GITHUB_REPO}/pulls/{pr_number}/files",
            params={"per_page": 100, "page": page},
        )
        if not batch:
            break
        files.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return files


def get_pr_reviews(pr_number: int) -> list[dict]:
    """Return all reviews for a PR."""
    return _github_get(
        f"/repos/{GITHUB_REPO}/pulls/{pr_number}/reviews",
        params={"per_page": 100},
    )


def get_pr_review_comments(pr_number: int) -> list[dict]:
    """Return all inline review comments for a PR."""
    comments: list[dict] = []
    page = 1
    while True:
        batch = _github_get(
            f"/repos/{GITHUB_REPO}/pulls/{pr_number}/comments",
            params={"per_page": 100, "page": page},
        )
        if not batch:
            break
        comments.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return comments


def get_latest_commit_sha(pr_number: int) -> str:
    """Return the HEAD commit SHA of the PR."""
    pr_data = _github_get(f"/repos/{GITHUB_REPO}/pulls/{pr_number}")
    return pr_data["head"]["sha"]


# ---------------------------------------------------------------------------
# Bot comment detection
# ---------------------------------------------------------------------------


def bot_review_state(pr_number: int) -> tuple[bool, bool]:
    """
    Returns (bot_has_reviewed, all_threads_resolved).

    'all_threads_resolved' is True when:
      - Bot left REQUEST_CHANGES and every bot inline comment has at least
        one reply from someone other than the bot, AND no unresolved threads
        remain (approximated: all bot comments have a reply).
    """
    reviews = get_pr_reviews(pr_number)
    bot_reviews = [r for r in reviews if r.get("user", {}).get("login") == BOT_USERNAME]

    if not bot_reviews:
        return False, False

    # Check if any bot review is REQUEST_CHANGES
    bot_requested_changes = any(r["state"] == "REQUEST_CHANGES" for r in bot_reviews)

    if not bot_requested_changes:
        # Bot reviewed but didn't request changes — treat threads as resolved
        return True, True

    # Bot requested changes — check if all inline comments have developer replies
    all_comments = get_pr_review_comments(pr_number)
    bot_review_ids = {r["id"] for r in bot_reviews}

    # Collect all bot inline comment IDs
    bot_comment_ids = {
        c["id"] for c in all_comments if c.get("user", {}).get("login") == BOT_USERNAME
    }

    if not bot_comment_ids:
        # Bot review had no inline comments — consider resolved
        return True, True

    # For each bot comment, check if there is a reply from someone else
    # GitHub stores replies as comments with in_reply_to_id matching the parent
    replied_to: set[int] = set()
    for c in all_comments:
        in_reply_to = c.get("in_reply_to_id")
        if in_reply_to and in_reply_to in bot_comment_ids:
            if c.get("user", {}).get("login") != BOT_USERNAME:
                replied_to.add(in_reply_to)

    all_resolved = replied_to >= bot_comment_ids
    return True, all_resolved


# ---------------------------------------------------------------------------
# PR classification
# ---------------------------------------------------------------------------

_SKIP_PATTERNS = (
    "migrations/",
    ".feature",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".lock",
    ".min.js",
    ".min.css",
)

_GENERATED_PATTERNS = (
    "migrations/",
    "schema.graphql",
    "openapi.json",
    "openapi.yaml",
)


def _is_reviewable(filename: str) -> bool:
    """True if the file should be included in review."""
    lower = filename.lower()
    for pat in _SKIP_PATTERNS:
        if pat in lower:
            return False
    return True


def _is_python(filename: str) -> bool:
    return filename.endswith(".py")


def _is_test_file(filename: str) -> bool:
    parts = Path(filename).parts
    return _is_python(filename) and (
        "tests" in parts or Path(filename).name.startswith("test_")
    )


def _is_frontend(filename: str) -> bool:
    return filename.startswith("frontend/") and (
        filename.endswith(".ts")
        or filename.endswith(".tsx")
        or filename.endswith(".js")
        or filename.endswith(".jsx")
    )


def classify_pr(files: list[dict]) -> str:
    """
    Returns one of: 'test', 'code', 'frontend', 'mixed'.
    """
    reviewable = [f for f in files if _is_reviewable(f["filename"])]
    if not reviewable:
        return "code"  # default fallback

    python_files = [f for f in reviewable if _is_python(f["filename"])]
    test_files = [f for f in python_files if _is_test_file(f["filename"])]
    frontend_files = [f for f in reviewable if _is_frontend(f["filename"])]

    total_py = len(python_files)
    total_fe = len(frontend_files)

    has_python = total_py > 0
    has_frontend = total_fe > 0

    if has_python and has_frontend:
        return "mixed"

    if has_frontend and not has_python:
        return "frontend"

    if has_python:
        test_ratio = len(test_files) / total_py if total_py else 0
        if test_ratio > 0.5:
            return "test"
        return "code"

    return "mixed"


# ---------------------------------------------------------------------------
# Guide loading
# ---------------------------------------------------------------------------


def load_guide(guide_filename: str) -> str:
    guide_path = GUIDES_DIR / guide_filename
    if not guide_path.exists():
        log.warning("Guide file not found: %s", guide_path)
        return f"[Guide file {guide_filename} not found — review using general best practices]"
    return guide_path.read_text(encoding="utf-8")


def load_guides_for_pr_type(pr_type: str) -> tuple[str, str]:
    """
    Returns (guide_content, special_note).
    special_note is a string to include in the review comment (may be empty).
    """
    if pr_type == "test":
        return load_guide("TEST_REVIEW_GUIDE.md"), ""

    if pr_type == "code":
        return load_guide("CODE_REVIEW_GUIDE.md"), ""

    if pr_type == "mixed":
        code_guide = load_guide("CODE_REVIEW_GUIDE.md")
        test_guide = load_guide("TEST_REVIEW_GUIDE.md")
        combined = (
            "=== CODE REVIEW GUIDE ===\n"
            + code_guide
            + "\n\n=== TEST REVIEW GUIDE ===\n"
            + test_guide
        )
        return combined, ""

    if pr_type == "frontend":
        return (
            load_guide("CODE_REVIEW_GUIDE.md"),
            (
                "**Note:** Automated frontend (TypeScript/React) review is not yet fully "
                "configured. This review applies general code guidelines only. A dedicated "
                "frontend review guide will be added in the future."
            ),
        )

    return load_guide("CODE_REVIEW_GUIDE.md"), ""


# ---------------------------------------------------------------------------
# Diff fetching and chunking
# ---------------------------------------------------------------------------


def get_file_diff(pr_number: int, filename: str) -> str:
    """Return raw diff content for a single file via PR files endpoint patch field."""
    files = get_pr_files(pr_number)
    for f in files:
        if f["filename"] == filename:
            return f.get("patch", "")
    return ""


def build_diff_chunks(pr_number: int, files: list[dict]) -> list[tuple[str, str]]:
    """
    Returns a list of (label, diff_text) tuples ready to send to Ollama.
    Each chunk is at most MAX_DIFF_CHARS characters.
    Files that exceed that are reviewed independently as individual chunks.
    Small files are batched together up to MAX_DIFF_CHARS.
    """
    reviewable = [
        f
        for f in files
        if _is_reviewable(f["filename"])
        and (
            _is_python(f["filename"]) or _is_frontend(f["filename"])
        )
        # Explicitly skip migrations (auto-generated, noisy)
        and "migrations/" not in f["filename"]
    ]

    if not reviewable:
        return []

    chunks: list[tuple[str, str]] = []
    current_label_parts: list[str] = []
    current_text_parts: list[str] = []
    current_length = 0

    for file_info in reviewable:
        patch = file_info.get("patch", "")
        if not patch:
            continue

        file_header = f"--- {file_info['filename']} ---\n"
        entry = file_header + patch

        if len(entry) > MAX_DIFF_CHARS:
            # Flush current batch first
            if current_text_parts:
                chunks.append(
                    (
                        ", ".join(current_label_parts),
                        "\n\n".join(current_text_parts),
                    )
                )
                current_label_parts = []
                current_text_parts = []
                current_length = 0

            # Add the large file as its own chunk (truncated if needed)
            truncated = entry[:MAX_DIFF_CHARS]
            if len(entry) > MAX_DIFF_CHARS:
                truncated += "\n... [diff truncated] ..."
            chunks.append((file_info["filename"], truncated))

        elif current_length + len(entry) > MAX_DIFF_CHARS:
            # Flush and start new batch
            chunks.append(
                (
                    ", ".join(current_label_parts),
                    "\n\n".join(current_text_parts),
                )
            )
            current_label_parts = [file_info["filename"]]
            current_text_parts = [entry]
            current_length = len(entry)

        else:
            current_label_parts.append(file_info["filename"])
            current_text_parts.append(entry)
            current_length += len(entry)

    # Flush remaining
    if current_text_parts:
        chunks.append(
            (
                ", ".join(current_label_parts),
                "\n\n".join(current_text_parts),
            )
        )

    return chunks


# ---------------------------------------------------------------------------
# Ollama integration
# ---------------------------------------------------------------------------

_OLLAMA_PROMPT_TEMPLATE = """\
You are a code reviewer. Read the REVIEW GUIDE below, then review the DIFF and output JSON.

=== REVIEW GUIDE ===
{guide_content}

=== DIFF TO REVIEW ===
{diff_chunk}

=== INSTRUCTIONS ===
Follow EXACTLY the OUTPUT FORMAT from the guide. Respond with valid JSON only.

If the guide does not specify an output format, use this default:
{{
  "event": "APPROVE" | "REQUEST_CHANGES" | "COMMENT",
  "summary": "<one sentence summary of the overall review>",
  "comments": [
    {{
      "path": "<file path relative to repo root>",
      "line": <integer line number in the diff>,
      "body": "<review comment text>"
    }}
  ]
}}

Rules:
- "event" must be one of: APPROVE, REQUEST_CHANGES, COMMENT
- "comments" must be an array (empty array if no inline comments)
- "path" must exactly match a filename from the diff
- "line" must be a positive integer visible in the diff
- Do NOT include any text outside the JSON object
"""


def call_ollama(guide_content: str, diff_chunk: str) -> Optional[dict]:
    """
    Call the Ollama API and return the parsed JSON response dict.
    Returns None on any failure (timeout, invalid JSON, network error).
    """
    prompt = _OLLAMA_PROMPT_TEMPLATE.format(
        guide_content=guide_content,
        diff_chunk=diff_chunk,
    )

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 1024,
        },
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        log.warning(
            "Ollama is unreachable at %s. Skipping review for this chunk.",
            OLLAMA_BASE_URL,
        )
        return None
    except requests.exceptions.Timeout:
        log.warning("Ollama request timed out after 120 s. Skipping chunk.")
        return None
    except requests.exceptions.RequestException as exc:
        log.warning("Ollama request failed: %s. Skipping chunk.", exc)
        return None

    raw_ollama = response.json().get("response", "")
    return _parse_ollama_json(raw_ollama)


def _parse_ollama_json(raw: str) -> Optional[dict]:
    """
    Extract and parse the JSON object from Ollama's raw text response.
    Handles cases where the model wraps JSON in markdown code fences.
    """
    if not raw.strip():
        log.warning("Ollama returned empty response.")
        return None

    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first and last fence lines
        inner_lines = []
        in_fence = False
        for line in lines:
            if line.startswith("```") and not in_fence:
                in_fence = True
                continue
            if line.startswith("```") and in_fence:
                break
            if in_fence:
                inner_lines.append(line)
        text = "\n".join(inner_lines)

    # Find the first '{' and last '}' to extract JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        log.warning(
            "Could not locate JSON object in Ollama response. Raw (first 500 chars): %s",
            raw[:500],
        )
        return None

    json_str = text[start : end + 1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as exc:
        log.warning(
            "JSON parse error from Ollama response: %s. Raw JSON attempt (first 500): %s",
            exc,
            json_str[:500],
        )
        return None


# ---------------------------------------------------------------------------
# Review merging and deduplication
# ---------------------------------------------------------------------------


def merge_chunk_results(chunk_results: list[dict]) -> dict:
    """
    Merge results from multiple diff chunks into a single review dict.

    Rules:
    - If ANY chunk returns REQUEST_CHANGES → overall event is REQUEST_CHANGES
    - If ALL chunks return APPROVE → overall event is APPROVE
    - Otherwise → COMMENT
    - Deduplicate comments by (path, line)
    - Keep at most MAX_COMMENTS, prioritising REQUEST_CHANGES comments
    - Summaries are concatenated
    """
    if not chunk_results:
        return {
            "event": "COMMENT",
            "summary": "No reviewable diff found.",
            "comments": [],
        }

    events = [r.get("event", "COMMENT") for r in chunk_results]
    if "REQUEST_CHANGES" in events:
        overall_event = "REQUEST_CHANGES"
    elif all(e == "APPROVE" for e in events):
        overall_event = "APPROVE"
    else:
        overall_event = "COMMENT"

    summaries = [
        r.get("summary", "").strip()
        for r in chunk_results
        if r.get("summary", "").strip()
    ]
    combined_summary = " | ".join(summaries) if summaries else "Review complete."

    # Collect and deduplicate comments
    seen: dict[tuple[str, int], dict] = {}
    request_change_comments: list[dict] = []
    other_comments: list[dict] = []

    for result in chunk_results:
        for comment in result.get("comments", []):
            path = comment.get("path", "")
            # line must be an integer; skip if missing or invalid
            try:
                line = int(comment.get("line", 0))
            except (TypeError, ValueError):
                continue
            if not path or line <= 0:
                continue

            key = (path, line)
            if key in seen:
                continue
            seen[key] = comment

            # Tag by severity for prioritisation
            body_lower = comment.get("body", "").lower()
            if any(
                kw in body_lower
                for kw in ("must", "critical", "error", "bug", "security", "required")
            ):
                request_change_comments.append(comment)
            else:
                other_comments.append(comment)

    # Prioritise critical comments, then fill with others up to MAX_COMMENTS
    final_comments = (request_change_comments + other_comments)[:MAX_COMMENTS]

    return {
        "event": overall_event,
        "summary": combined_summary,
        "comments": final_comments,
    }


# ---------------------------------------------------------------------------
# Posting reviews to GitHub
# ---------------------------------------------------------------------------


def post_review(
    pr_number: int,
    commit_sha: str,
    event: str,
    summary: str,
    comments: list[dict],
    special_note: str = "",
) -> None:
    """Post a pending GitHub PR review with optional inline comments."""
    body_parts = []
    if special_note:
        body_parts.append(special_note)
    body_parts.append(f"**Automated review by {BOT_USERNAME} via Ollama ({OLLAMA_MODEL})**\n\n{summary}")
    review_body = "\n\n".join(body_parts)

    # Build inline comments list in GitHub format
    github_comments = []
    for c in comments:
        path = c.get("path", "")
        try:
            line = int(c.get("line", 0))
        except (TypeError, ValueError):
            continue
        body = c.get("body", "").strip()
        if not path or line <= 0 or not body:
            continue
        github_comments.append(
            {
                "path": path,
                "line": line,
                "side": "RIGHT",
                "body": body,
            }
        )

    payload: dict[str, Any] = {
        "commit_id": commit_sha,
        "body": review_body,
        "event": event,
    }
    if github_comments:
        payload["comments"] = github_comments

    try:
        _github_post(f"/repos/{GITHUB_REPO}/pulls/{pr_number}/reviews", payload)
        log.info(
            "PR #%d: Posted %s review with %d inline comment(s).",
            pr_number,
            event,
            len(github_comments),
        )
    except requests.exceptions.RequestException as exc:
        log.error("PR #%d: Failed to post review: %s", pr_number, exc)


def post_approve_review(pr_number: int, commit_sha: str) -> None:
    """Post an APPROVE review after all threads appear resolved."""
    payload = {
        "commit_id": commit_sha,
        "body": (
            f"All previous review threads appear to be addressed. "
            f"Approving automatically. — {BOT_USERNAME} (Ollama/{OLLAMA_MODEL})"
        ),
        "event": "APPROVE",
    }
    try:
        _github_post(f"/repos/{GITHUB_REPO}/pulls/{pr_number}/reviews", payload)
        log.info("PR #%d: Auto-approved after threads resolved.", pr_number)
    except requests.exceptions.RequestException as exc:
        log.error("PR #%d: Failed to post auto-approve: %s", pr_number, exc)


# ---------------------------------------------------------------------------
# Ollama health check
# ---------------------------------------------------------------------------


def check_ollama_reachable() -> bool:
    """Return True if Ollama is reachable, False otherwise."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False


# ---------------------------------------------------------------------------
# Per-PR review orchestration
# ---------------------------------------------------------------------------


def review_pr(pr: dict) -> None:
    """Full review pipeline for a single PR."""
    pr_number = pr["number"]
    pr_title = pr.get("title", "(no title)")
    log.info("PR #%d: Starting review — %s", pr_number, pr_title)

    # Fetch files
    try:
        files = get_pr_files(pr_number)
    except requests.exceptions.RequestException as exc:
        log.error("PR #%d: Could not fetch files: %s", pr_number, exc)
        return

    # Classify
    pr_type = classify_pr(files)
    log.info("PR #%d: Classified as '%s'.", pr_number, pr_type)

    # Load guides
    guide_content, special_note = load_guides_for_pr_type(pr_type)

    # Frontend-only PRs get a comment with the special note but no deep review
    if pr_type == "frontend":
        try:
            commit_sha = get_latest_commit_sha(pr_number)
        except requests.exceptions.RequestException as exc:
            log.error("PR #%d: Could not get commit SHA: %s", pr_number, exc)
            return
        post_review(
            pr_number,
            commit_sha,
            event="COMMENT",
            summary="Frontend review is not yet fully automated. General guidelines applied.",
            comments=[],
            special_note=special_note,
        )
        return

    # Build diff chunks
    chunks = build_diff_chunks(pr_number, files)
    if not chunks:
        log.info("PR #%d: No reviewable diff chunks found. Skipping.", pr_number)
        return

    log.info("PR #%d: Reviewing %d diff chunk(s).", pr_number, len(chunks))

    # Call Ollama for each chunk
    chunk_results: list[dict] = []
    for idx, (label, diff_text) in enumerate(chunks, start=1):
        log.info(
            "PR #%d: Sending chunk %d/%d to Ollama (files: %s).",
            pr_number,
            idx,
            len(chunks),
            label[:80],
        )
        result = call_ollama(guide_content, diff_text)
        if result is None:
            log.warning(
                "PR #%d: Chunk %d returned no valid result. Skipping chunk.",
                pr_number,
                idx,
            )
            continue
        chunk_results.append(result)

    if not chunk_results:
        log.warning(
            "PR #%d: All chunks failed. No review will be posted.", pr_number
        )
        return

    # Merge results
    merged = merge_chunk_results(chunk_results)
    event = merged["event"]
    summary = merged["summary"]
    comments = merged["comments"]

    log.info(
        "PR #%d: Merged result — event=%s, comments=%d.",
        pr_number,
        event,
        len(comments),
    )

    # Get latest commit SHA for the review
    try:
        commit_sha = get_latest_commit_sha(pr_number)
    except requests.exceptions.RequestException as exc:
        log.error("PR #%d: Could not get commit SHA: %s", pr_number, exc)
        return

    # Post to GitHub
    post_review(
        pr_number,
        commit_sha,
        event=event,
        summary=summary,
        comments=comments,
        special_note=special_note,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    log.info("PR Review Bot starting. Repo: %s, Bot: %s", GITHUB_REPO, BOT_USERNAME)

    if not GITHUB_TOKEN:
        log.error("GITHUB_TOKEN is not set. Cannot continue.")
        raise SystemExit(1)

    # Verify Ollama is reachable before doing any work
    if not check_ollama_reachable():
        log.warning(
            "Ollama is not reachable at %s. Exiting gracefully — cron will retry in 3 hours.",
            OLLAMA_BASE_URL,
        )
        raise SystemExit(0)

    log.info("Ollama reachable at %s. Model: %s.", OLLAMA_BASE_URL, OLLAMA_MODEL)

    # Fetch all open PRs
    try:
        prs = list_open_prs()
    except requests.exceptions.RequestException as exc:
        log.error("Failed to list open PRs: %s", exc)
        raise SystemExit(1)

    if not prs:
        log.info("No open PRs found. Exiting.")
        raise SystemExit(0)

    for pr in prs:
        pr_number = pr["number"]
        is_draft = pr.get("draft", False)
        labels = get_pr_labels(pr)

        log.info(
            "PR #%d: draft=%s, labels=%s", pr_number, is_draft, labels
        )

        # Skip draft PRs unless they have ready-for-CI label
        if is_draft and "ready-for-CI" not in labels:
            log.info("PR #%d: Draft without 'ready-for-CI'. Skipping.", pr_number)
            continue

        # Determine bot's prior review state
        try:
            bot_has_reviewed, all_resolved = bot_review_state(pr_number)
        except requests.exceptions.RequestException as exc:
            log.error(
                "PR #%d: Could not determine bot review state: %s", pr_number, exc
            )
            continue

        if bot_has_reviewed and all_resolved:
            # Auto-approve: all threads resolved
            log.info(
                "PR #%d: Bot has reviewed and all threads resolved. Auto-approving.",
                pr_number,
            )
            try:
                commit_sha = get_latest_commit_sha(pr_number)
                post_approve_review(pr_number, commit_sha)
            except requests.exceptions.RequestException as exc:
                log.error("PR #%d: Auto-approve failed: %s", pr_number, exc)
            continue

        if bot_has_reviewed and not all_resolved:
            # Still waiting for developer to address feedback
            log.info(
                "PR #%d: Bot has reviewed but threads unresolved. Waiting for developer.",
                pr_number,
            )
            continue

        # Bot has NOT reviewed yet — start review
        # Only review if PR has ready-for-CI label OR is not a draft
        if not is_draft or "ready-for-CI" in labels:
            try:
                review_pr(pr)
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "PR #%d: Unexpected error during review: %s", pr_number, exc, exc_info=True
                )
            # Small delay between PRs to be polite to both APIs
            time.sleep(2)
        else:
            log.info(
                "PR #%d: Does not meet review criteria (draft, no ready-for-CI label).",
                pr_number,
            )

    log.info("PR Review Bot finished.")


if __name__ == "__main__":
    main()
