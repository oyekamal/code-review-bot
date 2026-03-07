"""Persistent review database — tracks what the bot has already reviewed."""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(".bot/reviews.json")


class ReviewDB:
    """Simple JSON store keyed by project → pr_number.

    Stored per PR:
      head_sha       – HEAD commit SHA at time of review
      reviewed_at    – ISO timestamp
      event          – APPROVE / REQUEST_CHANGES / COMMENT
      files_reviewed – count of backend files reviewed
      comments_posted – count of inline comments posted
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
        """Persist a review result."""
        if project not in self._data:
            self._data[project] = {}

        self._data[project][str(pr_number)] = {
            "pr_number": pr_number,
            "title": title,
            "head_sha": head_sha,
            "reviewed_at": datetime.now().isoformat(),
            "event": event,
            "files_reviewed": files_reviewed,
            "comments_posted": comments_posted,
        }
        self._save()
        logger.info(f"  💾 Recorded review for PR #{pr_number} ({event}, sha={head_sha[:7]})")

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
