"""Persistent review database — tracks what the bot has already reviewed."""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(".bot/reviews.json")


class ReviewDB:
    """Simple JSON store keyed by project → pr_number.

    Stored per PR:
      head_sha        – HEAD commit SHA at time of review
      reviewed_at     – ISO timestamp
      event           – APPROVE / REQUEST_CHANGES / COMMENT
      files_reviewed  – count of backend files reviewed
      comments_posted – count of inline comments posted
      comments        – list of individual comment records (see record_comments())
    """

    def __init__(self):
        self._data: Dict = self._load()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def already_reviewed(self, project: str, pr_number: int, current_sha: str) -> bool:
        """Return True if we already reviewed this exact commit."""
        record = self._get(project, pr_number)
        if not record:
            return False
        return record.get("head_sha") == current_sha

    def record(
        self,
        project: str,
        pr_number: int,
        head_sha: str,
        event: str,
        files_reviewed: int,
        comments_posted: int,
        title: str = "",
    ) -> None:
        """Persist a review result. Preserves any existing per-comment history."""
        if project not in self._data:
            self._data[project] = {}

        # Preserve existing per-comment records when updating a PR entry
        existing_comments = self._data.get(project, {}).get(str(pr_number), {}).get("comments", [])

        self._data[project][str(pr_number)] = {
            "pr_number": pr_number,
            "title": title,
            "head_sha": head_sha,
            "reviewed_at": datetime.now().isoformat(),
            "event": event,
            "files_reviewed": files_reviewed,
            "comments_posted": comments_posted,
            "comments": existing_comments,
        }
        self._save()
        logger.info(f"  💾 Recorded review for PR #{pr_number} ({event}, sha={head_sha[:7]})")

    def get_comments(self, project: str, pr_number: int) -> List[Dict]:
        """Return the stored per-comment records for a PR.

        Each record has: path, line, body, posted_at, status, resolved_at, user_reply
        """
        record = self._get(project, pr_number)
        if not record:
            return []
        return record.get("comments", [])

    def record_comments(self, project: str, pr_number: int, comments: List[Dict]) -> None:
        """Append newly posted comments to this PR's history.

        Each comment dict should have at minimum: path, line, body.
        posted_at and status will be set automatically if missing.
        """
        if project not in self._data:
            self._data[project] = {}
        key = str(pr_number)
        if key not in self._data[project]:
            self._data[project][key] = {"pr_number": pr_number, "comments": []}
        if "comments" not in self._data[project][key]:
            self._data[project][key]["comments"] = []

        now = datetime.now().isoformat()
        for c in comments:
            entry = {
                "path": c.get("path", ""),
                "line": c.get("line", 0),
                "body": c.get("body", ""),
                "posted_at": c.get("posted_at", now),
                "status": c.get("status", "unresolved"),
                "resolved_at": c.get("resolved_at"),
                "user_reply": c.get("user_reply"),
            }
            self._data[project][key]["comments"].append(entry)

        self._save()
        logger.info(f"  💾 Stored {len(comments)} comment record(s) for PR #{pr_number}")

    def sync_resolved_comments(
        self, project: str, pr_number: int, thread_details: List[Dict]
    ) -> int:
        """Mark stored comments as resolved based on thread data from GitHub.

        thread_details: list of {path, line, is_resolved} for bot-authored threads.
        Returns count of newly resolved comments.
        """
        record = self._get(project, pr_number)
        if not record or not record.get("comments"):
            return 0

        newly_resolved = 0
        now = datetime.now().isoformat()
        for comment in record["comments"]:
            if comment.get("status") == "resolved":
                continue
            for thread in thread_details:
                if not thread.get("is_resolved"):
                    continue
                t_path = thread.get("path", "")
                t_line = thread.get("line") or 0
                c_path = comment.get("path", "")
                c_line = comment.get("line") or 0
                if t_path == c_path and abs(t_line - c_line) <= 5:
                    comment["status"] = "resolved"
                    comment["resolved_at"] = now
                    newly_resolved += 1
                    break

        if newly_resolved:
            self._save()
        return newly_resolved

    def record_user_replies(
        self, project: str, pr_number: int, replies: List[Dict]
    ) -> int:
        """Store user replies against matching bot comments.

        replies: list of {path, line, user_login, body} for non-bot comments.
        Returns count of comments updated with a reply.
        """
        record = self._get(project, pr_number)
        if not record or not record.get("comments"):
            return 0

        updated = 0
        for comment in record["comments"]:
            if comment.get("user_reply"):
                continue  # Already has a reply stored
            c_path = comment.get("path", "")
            c_line = comment.get("line") or 0
            for reply in replies:
                r_path = reply.get("path", "")
                r_line = reply.get("line") or 0
                if r_path == c_path and abs(r_line - c_line) <= 5:
                    comment["user_reply"] = reply.get("body", "")
                    updated += 1
                    break

        if updated:
            self._save()
        return updated

    def get_stats(self, project: str) -> Dict:
        """Return aggregate stats for a project."""
        records = list(self._data.get(project, {}).values())
        return {
            "total_reviewed": len(records),
            "approved": sum(1 for r in records if r["event"] == "APPROVE"),
            "changes_requested": sum(1 for r in records if r["event"] == "REQUEST_CHANGES"),
            "total_comments": sum(r.get("comments_posted", 0) for r in records),
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _get(self, project: str, pr_number: int) -> Optional[Dict]:
        return self._data.get(project, {}).get(str(pr_number))

    def _load(self) -> Dict:
        if DB_PATH.exists():
            try:
                return json.loads(DB_PATH.read_text())
            except Exception as e:
                logger.warning(f"⚠ Could not load review DB: {e}")
        return {}

    def _save(self) -> None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        DB_PATH.write_text(json.dumps(self._data, indent=2))
