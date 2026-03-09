"""Smart PR reviewer with auto-discovery."""
from pathlib import Path
from typing import Dict, Tuple, List, Optional
import json
import logging
from datetime import datetime
import tempfile
import subprocess

from ..config.settings import ProjectSettings
from ..integrations.github.client import GitHubClient
from ..integrations.llm.base import LLMProvider
from ..integrations.llm.ollama import OllamaProvider
from ..integrations.llm.anthropic import AnthropicProvider
from ..core.detector import FrameworkDetector
from ..core.guide_loader import GuideLoader
from ..core.diff_parser import DiffParser
from ..core.review_db import ReviewDB

logger = logging.getLogger(__name__)


class SmartReviewer:
    """Intelligent PR reviewer with auto-discovery."""
    
    def __init__(self, config: ProjectSettings):
        """Initialize smart reviewer.
        
        Args:
            config: Project configuration
        """
        self.config = config
        self.github = GitHubClient(
            config.get_github_token(),
            config.repo
        )
        self.detector = FrameworkDetector()
        self.guide_loader = GuideLoader()
        self.llm = self._create_llm()
        self.bot_login = self.github.get_authenticated_user()
        self.db = ReviewDB()

        logger.info(f"🚀 SmartReviewer initialized for {config.name} (bot: {self.bot_login})")
    
    def _create_llm(self) -> LLMProvider:
        """Create LLM provider based on config."""
        if self.config.llm.provider == "ollama":
            return OllamaProvider(
                self.config.llm.base_url,
                self.config.llm.model
            )
        elif self.config.llm.provider == "anthropic":
            api_key = self.config.get_llm_api_key()
            if not api_key:
                raise ValueError(f"Anthropic API key not found in env: {self.config.llm.api_key_env}")
            return AnthropicProvider(api_key, self.config.llm.model)
        else:
            raise ValueError(f"Unknown LLM provider: {self.config.llm.provider}")
    
    def discover_project(self, repo_path: str) -> Tuple[List[str], dict]:
        """Analyze project and cache discovery results.

        Args:
            repo_path: Path to cloned repository

        Returns:
            Tuple of (frameworks, guides_dict)
        """
        logger.info(f"🔍 Discovering project: {self.config.name}")

        # Detect frameworks
        frameworks = []
        if self.config.discovery.auto_detect:
            frameworks = self.detector.detect(repo_path)
        else:
            frameworks = self.config.discovery.frameworks
            logger.info(f"  Using manual frameworks: {frameworks}")

        # Load custom guides individually
        guides = self.guide_loader.load_guides_dict(
            repo_path,
            self.config.discovery.guide_files
        )

        # Cache results (save profile using combined string for hash)
        self._save_profile(frameworks, "\n".join(guides.values()))

        return frameworks, guides

    @staticmethod
    def _is_backend_file(file_path: str) -> bool:
        """Return True only for Django/Python backend files."""
        SKIP_EXTENSIONS = {
            ".js", ".jsx", ".ts", ".tsx",
            ".css", ".scss", ".sass", ".less",
            ".html", ".vue", ".svelte",
            ".json", ".md", ".yaml", ".yml",
            ".toml", ".ini", ".cfg", ".env",
            ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico",
            ".lock", ".map",
        }
        from pathlib import Path as _Path
        return _Path(file_path).suffix.lower() not in SKIP_EXTENSIONS

    def _select_guide(self, file_path: str, guides: dict) -> str:
        """Pick the right guide string for a file.

        Test files → TEST_REVIEW_GUIDE; everything else → CODE_REVIEW_GUIDE.
        Falls back to the combined guides if a specific one isn't found.
        """
        import os
        name = os.path.basename(file_path)
        parts = file_path.replace("\\", "/").split("/")
        is_test = name.startswith("test_") or name.endswith("_test.py") or "tests" in parts

        for guide_path, content in guides.items():
            key = guide_path.upper()
            if is_test and "TEST" in key:
                logger.info(f"    📋 Using test guide for {file_path}")
                return content
            if not is_test and "CODE" in key and "TEST" not in key:
                logger.info(f"    📋 Using code guide for {file_path}")
                return content

        # Fallback: combine all guides
        if guides:
            return "\n\n".join(guides.values())
        return self.guide_loader._get_default_guide()

    def _deduplicate_comments(self, pr_number: int, new_comments: List[Dict]) -> List[Dict]:
        """Remove comments the bot already posted on the same file/line area.

        Args:
            pr_number: PR number to check for existing bot comments
            new_comments: Proposed new comments from the LLM

        Returns:
            Filtered list with duplicates removed
        """
        existing = self.github.get_bot_review_comments(pr_number)
        # Build set of (path, line) the bot already commented on
        bot_spots = {
            (c["path"], c["line"])
            for c in existing
            if c["user"] == self.bot_login
        }

        if not bot_spots:
            return new_comments

        filtered = []
        for comment in new_comments:
            path = comment.get("path", "")
            line = comment.get("line", 0)
            # Skip if bot already has a comment within 20 lines on the same file
            # (20-line tolerance handles line number shifts from new commits)
            already_commented = any(
                ep == path and abs(el - line) <= 20
                for ep, el in bot_spots
            )
            if already_commented:
                logger.info(f"  ⏭ Skipping duplicate comment on {path}:{line}")
            else:
                filtered.append(comment)

        skipped = len(new_comments) - len(filtered)
        if skipped:
            logger.info(f"  🔄 Deduplicated {skipped} already-posted comment(s)")
        return filtered

    def _bot_has_pending_request_changes(self, pr_number: int) -> bool:
        """Return True if the bot's most recent review is REQUEST_CHANGES."""
        reviews = self.github.get_existing_reviews(pr_number)
        bot_reviews = [r for r in reviews if r["user"] == self.bot_login]
        if bot_reviews:
            return bot_reviews[-1]["state"] == "CHANGES_REQUESTED"
        return False

    def review_pr(self, pr_number: int, repo_path: Optional[str] = None) -> Dict:
        """Review a pull request.
        
        Args:
            pr_number: PR number to review
            repo_path: Optional path to cloned repo (only needed for remote guide files)
            
        Returns:
            Review result dictionary
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 Reviewing PR #{pr_number} in {self.config.name}")
        logger.info(f"{'='*60}\n")
        
        try:
            # Get PR data
            pr = self.github.get_pr(pr_number)
            diff = self.github.get_pr_diff(pr_number)
            files = self.github.get_pr_files(pr_number)
            
            # Check if we need to clone (only if guides are remote or first-time detection)
            need_clone = self._need_repo_clone()
            if need_clone and repo_path is None:
                repo_path = self._clone_repo()
            elif repo_path is None:
                # Use current directory for local guides
                repo_path = "."
            
            # Load or discover project profile
            frameworks, guides = self._load_or_discover_profile(repo_path)
            
            # Build PR context
            pr_context = {
                "number": pr_number,
                "title": pr.title,
                "description": pr.body or "",
                "author": pr.user.login,
                "files_changed": len(files),
                "frameworks": frameworks,
            }
            
            # Parse diff to split by files
            diff_parser = DiffParser(diff)
            file_diffs = diff_parser.split_by_files()

            logger.info(f"🧠 Generating review (file-by-file)...")
            logger.info(f"  📂 Reviewing {len(file_diffs)} files separately")

            # Review files one by one
            all_comments = []
            files_reviewed = 0
            files_with_issues = 0

            for file_path, file_diff in file_diffs.items():
                # Skip empty files or files with no actual changes
                if not file_diff.strip() or len(file_diff) < 50:
                    continue

                # Skip non-backend files
                if not self._is_backend_file(file_path):
                    logger.info(f"  ⏭ Skipping non-backend file: {file_path}")
                    continue

                files_reviewed += 1
                logger.info(f"  📄 {files_reviewed}/{len(file_diffs)}: {file_path}")

                # Create file-specific context
                file_context = pr_context.copy()
                file_context["current_file"] = file_path
                file_context["files_changed"] = 1  # Single file context

                # Pick guide based on file type
                file_guide = self._select_guide(file_path, guides)

                # Review this file
                file_review = self.llm.review(file_guide, file_diff, file_context)

                # Collect comments
                file_comments = file_review.get("comments", [])
                if file_comments:
                    files_with_issues += 1
                    logger.info(f"    ⚠ Found {len(file_comments)} issues")
                    all_comments.extend(file_comments)
                else:
                    logger.info(f"    ✓ No issues found")
            
            # Remove comments the bot already posted
            all_comments = self._deduplicate_comments(pr_number, all_comments)

            # Limit total comments if needed
            if len(all_comments) > self.config.review.max_comments:
                logger.info(f"  ⚠ Limiting comments from {len(all_comments)} to {self.config.review.max_comments}")
                all_comments = all_comments[:self.config.review.max_comments]

            # Determine review event
            had_pending_request = self._bot_has_pending_request_changes(pr_number)

            if all_comments:
                event = "REQUEST_CHANGES"
            elif files_reviewed > 0 or (self.config.review.auto_approve_on_resolution and had_pending_request):
                # No new issues found: approve.
                # If bot previously requested changes and everything is now clean,
                # this APPROVE will dismiss the old REQUEST_CHANGES review.
                event = "APPROVE"
                if had_pending_request:
                    logger.info("  ✅ All previous issues appear resolved — approving PR")
            else:
                event = "COMMENT"

            review_result = {
                "event": event,
                "summary": f"Reviewed {files_reviewed} files. Found issues in {files_with_issues} files ({len(all_comments)} comments).",
                "comments": all_comments,
                # Internal metadata for DB recording (stripped before posting)
                "_files_reviewed": files_reviewed,
                "_title": pr.title,
            }
            
            logger.info(f"\n✅ Review completed:")
            logger.info(f"  Event: {review_result.get('event')}")
            logger.info(f"  Files reviewed: {files_reviewed}")
            logger.info(f"  Files with issues: {files_with_issues}")
            logger.info(f"  Total comments: {len(all_comments)}")
            
            return review_result
            
        except Exception as e:
            logger.error(f"❌ Review failed: {e}")
            raise
    
    def post_review(self, pr_number: int, review_result: Dict, head_sha: str = "") -> None:
        """Post review to GitHub and record it in the review DB.

        Args:
            pr_number: PR number
            review_result: Review dictionary from review_pr
            head_sha: HEAD commit SHA (used to track what was reviewed)
        """
        logger.info(f"📤 Posting review to PR #{pr_number}")
        try:
            self.github.post_review(pr_number, review_result)
            logger.info(f"  ✓ Review posted successfully")
            # Persist so we skip this SHA on the next run
            if head_sha:
                self.db.record(
                    project=self.config.name,
                    pr_number=pr_number,
                    head_sha=head_sha,
                    event=review_result.get("event", "COMMENT"),
                    files_reviewed=review_result.get("_files_reviewed", 0),
                    comments_posted=len(review_result.get("comments", [])),
                    title=review_result.get("_title", ""),
                )
        except Exception as e:
            logger.error(f"  ❌ Failed to post review: {e}")
            raise
    
    def review_and_post(self, pr_number: int, repo_path: Optional[str] = None) -> Dict:
        """Review and post in one step.
        
        Args:
            pr_number: PR number
            repo_path: Optional path to cloned repo
            
        Returns:
            Review result
        """
        head_sha = self.github.get_pr(pr_number).head.sha
        review_result = self.review_pr(pr_number, repo_path)
        self.post_review(pr_number, review_result, head_sha=head_sha)
        return review_result
    
    def review_all_open_prs(self, repo_path: Optional[str] = None) -> List[Dict]:
        """Review all open PRs in the repository.
        
        Args:
            repo_path: Optional path to cloned repo
            
        Returns:
            List of review results
        """
        target = self.config.review.target_branch
        logger.info(f"📋 Reviewing open PRs in {self.config.name}" + (f" targeting '{target}'" if target else ""))

        prs = self.github.list_open_prs(base_branch=target)
        results = []
        skipped = 0

        for pr_data in prs:
            pr_number = pr_data["number"]
            head_sha = pr_data.get("head_sha", "")

            # Skip PRs authored by the bot account itself
            pr_author = pr_data.get("author", "")
            if pr_author == self.bot_login:
                logger.info(f"  ⏭ PR #{pr_number} authored by bot ({self.bot_login}) — skipping")
                skipped += 1
                continue

            # Skip if we already reviewed this exact commit
            if head_sha and self.db.already_reviewed(self.config.name, pr_number, head_sha):
                logger.info(f"  ⏭ PR #{pr_number} unchanged since last review (sha={head_sha[:7]}) — skipping")
                skipped += 1
                continue

            try:
                review_result = self.review_pr(pr_number, repo_path)
                self.post_review(pr_number, review_result, head_sha=head_sha)
                results.append({"pr_number": pr_number, "success": True, "result": review_result})
            except Exception as e:
                logger.error(f"  ❌ Failed to review PR #{pr_number}: {e}")
                results.append({"pr_number": pr_number, "success": False, "error": str(e)})

        stats = self.db.get_stats(self.config.name)
        logger.info(f"\n✅ Completed: {len(results)} reviewed, {skipped} skipped (no new commits)")
        logger.info(f"  DB totals — reviewed: {stats['total_reviewed']}, comments: {stats['total_comments']}, approved: {stats['approved']}, changes requested: {stats['changes_requested']}")
        return results
    
    def _clone_repo(self) -> str:
        """Clone repository to temp directory.
        
        Returns:
            Path to cloned repository
        """
        temp_dir = Path(tempfile.mkdtemp(prefix=f"pr_review_{self.config.name}_"))
        logger.info(f"📥 Cloning {self.config.repo} to {temp_dir}")
        
        try:
            subprocess.run(
                ["git", "clone", f"https://github.com/{self.config.repo}.git", str(temp_dir)],
                check=True,
                capture_output=True
            )
            logger.info(f"  ✓ Repository cloned")
            return str(temp_dir)
        except subprocess.CalledProcessError as e:
            logger.error(f"  ❌ Clone failed: {e.stderr.decode()}")
            raise
    
    def _save_profile(self, frameworks: List[str], guides: str) -> None:
        """Save discovery profile to cache.
        
        Args:
            frameworks: Detected frameworks
            guides: Combined guide content
        """
        profile_dir = Path(".bot/profiles")
        profile_dir.mkdir(parents=True, exist_ok=True)
        
        profile = {
            "project": self.config.name,
            "frameworks": frameworks,
            "guide_hash": hash(guides),
            "guide_length": len(guides),
            "timestamp": datetime.now().isoformat(),
        }
        
        profile_path = profile_dir / f"{self.config.name}.json"
        with open(profile_path, "w") as f:
            json.dump(profile, f, indent=2)
        
        logger.info(f"💾 Saved profile to {profile_path}")
    
    def _need_repo_clone(self) -> bool:
        """Check if we need to clone the repository.
        
        Returns:
            True if clone is needed, False if we can use local files
        """
        # Check if all guide files are local (relative paths)
        all_local = all(
            not Path(gf).is_absolute() and not gf.startswith(('http://', 'https://', 'git@'))
            for gf in self.config.discovery.guide_files
        )
        
        # Check if we have a cached profile
        profile_path = Path(f".bot/profiles/{self.config.name}.json")
        has_cache = profile_path.exists()
        
        # Only need clone if: guides are remote OR (no cache AND auto_detect enabled)
        if not all_local:
            logger.info("  ⚠ Remote guide files detected, will clone repo")
            return True
        
        if not has_cache and self.config.discovery.auto_detect:
            logger.info("  ⚠ First-time detection, will clone repo")
            return True
        
        logger.info("  ✓ Using local guides, skipping clone")
        return False
    
    def _load_or_discover_profile(self, repo_path: str) -> Tuple[List[str], dict]:
        """Load cached profile or discover.

        Args:
            repo_path: Path to repository (or '.' for current directory)

        Returns:
            Tuple of (frameworks, guides_dict)
        """
        profile_path = Path(f".bot/profiles/{self.config.name}.json")

        if profile_path.exists():
            logger.info(f"📂 Loading cached profile from {profile_path}")
            try:
                with open(profile_path) as f:
                    profile = json.load(f)

                # Check if profile is recent (less than 1 day old)
                timestamp = datetime.fromisoformat(profile["timestamp"])
                age_hours = (datetime.now() - timestamp).total_seconds() / 3600

                if age_hours < 24:
                    frameworks = profile["frameworks"]
                    guides = self.guide_loader.load_guides_dict(
                        repo_path,
                        self.config.discovery.guide_files
                    )
                    logger.info(f"  ✓ Using cached frameworks: {frameworks}")
                    return frameworks, guides
                else:
                    logger.info(f"  ⚠ Profile is {age_hours:.1f}h old, re-discovering...")
            except Exception as e:
                logger.warning(f"  ⚠ Failed to load profile: {e}")

        # Discover fresh (or use manual frameworks)
        if self.config.discovery.auto_detect and repo_path != ".":
            return self.discover_project(repo_path)
        else:
            frameworks = self.config.discovery.frameworks or ["django"]
            guides = self.guide_loader.load_guides_dict(
                repo_path,
                self.config.discovery.guide_files
            )
            self._save_profile(frameworks, "\n".join(guides.values()))
            logger.info(f"  ✓ Using frameworks: {frameworks}")
            return frameworks, guides
