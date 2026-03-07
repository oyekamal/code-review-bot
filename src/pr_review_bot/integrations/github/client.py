"""GitHub API integration."""
from github import Github, GithubException
from github.PullRequest import PullRequest
from github.Repository import Repository
from typing import List, Dict, Optional
import logging
import requests

from pr_review_bot.core.diff_parser import DiffParser

logger = logging.getLogger(__name__)


class GitHubClient:
    """GitHub API client for PR operations."""
    
    def __init__(self, token: str, repo_fullname: str):
        """Initialize GitHub client.
        
        Args:
            token: GitHub personal access token
            repo_fullname: Repository in format 'owner/repo'
        """
        self.github = Github(token)
        self.token = token
        self.repo_fullname = repo_fullname
        self._repo: Optional[Repository] = None
        
        logger.info(f"📡 Initializing GitHub client for {repo_fullname}")
    
    @property
    def repo(self) -> Repository:
        """Get repository object (cached)."""
        if self._repo is None:
            self._repo = self.github.get_repo(self.repo_fullname)
            logger.info(f"  ✓ Connected to {self._repo.full_name}")
        return self._repo
    
    def list_open_prs(self, base_branch: Optional[str] = None) -> List[Dict]:
        """List open pull requests, optionally filtered by base branch.

        Args:
            base_branch: Only return PRs targeting this branch (e.g. 'develop').
                         If None, all open PRs are returned.

        Returns:
            List of PR dictionaries with basic info
        """
        branch_label = f" → {base_branch}" if base_branch else ""
        logger.info(f"📋 Fetching open PRs from {self.repo_fullname}{branch_label}")

        try:
            kwargs = dict(state='open', sort='created', direction='desc')
            if base_branch:
                kwargs['base'] = base_branch
            prs = self.repo.get_pulls(**kwargs)
            pr_list = []

            for pr in prs:
                pr_list.append({
                    "number": pr.number,
                    "title": pr.title,
                    "author": pr.user.login,
                    "url": pr.html_url,
                    "base": pr.base.ref,
                    "head_sha": pr.head.sha,
                    "created_at": pr.created_at.isoformat(),
                    "updated_at": pr.updated_at.isoformat(),
                })
                logger.info(f"  #{pr.number}: {pr.title} by {pr.user.login} (→ {pr.base.ref})")

            logger.info(f"  Total: {len(pr_list)} open PRs")
            return pr_list

        except GithubException as e:
            logger.error(f"  ❌ Error fetching PRs: {e}")
            raise
    
    def get_pr(self, pr_number: int) -> PullRequest:
        """Get a specific pull request.
        
        Args:
            pr_number: PR number
            
        Returns:
            PullRequest object
        """
        logger.info(f"🔍 Fetching PR #{pr_number}")
        try:
            pr = self.repo.get_pull(pr_number)
            logger.info(f"  ✓ {pr.title} by {pr.user.login}")
            return pr
        except GithubException as e:
            logger.error(f"  ❌ Error fetching PR #{pr_number}: {e}")
            raise
    
    def get_pr_diff(self, pr_number: int) -> str:
        """Get the unified diff for a pull request.
        
        Args:
            pr_number: PR number
            
        Returns:
            Unified diff as string
        """
        logger.info(f"📥 Fetching diff for PR #{pr_number}")
        
        try:
            # Use REST API directly for diff
            url = f"https://api.github.com/repos/{self.repo_fullname}/pulls/{pr_number}"
            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3.diff",
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            diff = response.text
            lines = len(diff.split('\n'))
            logger.info(f"  ✓ Fetched diff: {lines} lines, {len(diff)} bytes")
            
            return diff
            
        except Exception as e:
            logger.error(f"  ❌ Error fetching diff: {e}")
            raise
    
    def get_pr_files(self, pr_number: int) -> List[Dict]:
        """Get list of files changed in a PR.
        
        Args:
            pr_number: PR number
            
        Returns:
            List of file dictionaries
        """
        logger.info(f"📂 Fetching changed files for PR #{pr_number}")
        
        try:
            pr = self.get_pr(pr_number)
            files = pr.get_files()
            
            file_list = []
            for f in files:
                file_list.append({
                    "filename": f.filename,
                    "status": f.status,  # added, removed, modified
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "changes": f.changes,
                    "patch": f.patch if hasattr(f, 'patch') else None,
                })
                logger.info(f"  {f.status:8s} {f.filename} (+{f.additions}/-{f.deletions})")
            
            logger.info(f"  Total: {len(file_list)} files changed")
            return file_list
            
        except GithubException as e:
            logger.error(f"  ❌ Error fetching files: {e}")
            raise
    
    def post_review(self, pr_number: int, review_data: Dict) -> None:
        """Post a review to a pull request.
        
        Args:
            pr_number: PR number
            review_data: Review dictionary with 'event', 'summary', 'comments'
        """
        logger.info(f"💬 Posting review to PR #{pr_number}")
        
        try:
            pr = self.get_pr(pr_number)

            event = review_data.get("event", "COMMENT")
            summary = review_data.get("summary", "")
            # Strip internal metadata keys (prefixed with _) before posting
            comments = review_data.get("comments", [])
            
            logger.info(f"  Event: {event}")
            logger.info(f"  Summary: {summary[:100]}...")
            logger.info(f"  Comments: {len(comments)}")
            
            # Get PR diff and parse it for line number validation
            diff = self.get_pr_diff(pr_number)
            diff_parser = DiffParser(diff)
            
            # Get actual changed files for path validation
            changed_files = self.get_pr_files(pr_number)
            valid_paths = {f["filename"] for f in changed_files}
            
            # Log diff summary
            summary_dict = diff_parser.get_file_summary()
            logger.info(f"  Diff summary: {len(summary_dict)} files with changes")
            
            # Create review comments with path and line number validation
            review_comments = []
            skipped = 0
            for comment in comments:
                try:
                    comment_path = comment["path"]
                    comment_line = comment["line"]
                    
                    # Try to match the path (LLM might use shortened paths)
                    matched_path = self._match_file_path(comment_path, valid_paths)
                    
                    if not matched_path:
                        skipped += 1
                        logger.warning(f"    ⚠ Skipped (path not found): {comment_path}")
                        continue
                    
                    # Validate line number against diff
                    if not diff_parser.validate_comment(matched_path, comment_line):
                        valid_lines = diff_parser.get_valid_lines_for_file(matched_path)
                        if valid_lines:
                            # Try to find nearest valid line
                            nearest = min(valid_lines, key=lambda x: abs(x - comment_line))
                            if abs(nearest - comment_line) <= 10:
                                logger.info(f"    ℹ Adjusted line {comment_line} → {nearest} for {matched_path}")
                                comment_line = nearest
                            else:
                                skipped += 1
                                logger.warning(f"    ⚠ Skipped (invalid line {comment_line}): {matched_path}")
                                logger.warning(f"      Valid lines: {valid_lines[:5]}...")
                                continue
                        else:
                            skipped += 1
                            logger.warning(f"    ⚠ Skipped (no valid lines found): {matched_path}")
                            continue
                    
                    review_comment = {
                        "path": matched_path,
                        "body": comment["body"],
                        "line": comment_line,
                        "side": "RIGHT",
                    }
                    review_comments.append(review_comment)
                    logger.info(f"    ✓ Comment on {matched_path}:{comment_line}")
                        
                except Exception as e:
                    skipped += 1
                    logger.warning(f"    ⚠ Skipping comment: {e}")
            
            if skipped > 0:
                logger.warning(f"  ⚠ Skipped {skipped} comments due to invalid paths/lines")
            
            # Post the review
            if review_comments:
                pr.create_review(
                    body=summary,
                    event=event,
                    comments=review_comments
                )
            else:
                # Just post a comment if no line comments
                logger.info(f"  ℹ No valid line comments, posting summary only")
                pr.create_issue_comment(f"**Review Summary**\n\n{summary}")
            
            logger.info(f"  ✓ Review posted successfully")
            
        except GithubException as e:
            logger.error(f"  ❌ Error posting review: {e}")
            raise
    
    def _match_file_path(self, comment_path: str, valid_paths: set) -> Optional[str]:
        """Match a comment path to an actual file path in the PR.
        
        LLMs often generate shortened paths like 'tests/test_file.py' when the actual
        path is 'app/module/tests/test_file.py'. This method tries to match them.
        
        Args:
            comment_path: Path from LLM comment
            valid_paths: Set of actual file paths in the PR
            
        Returns:
            Matched full path or None if no match found
        """
        # Exact match
        if comment_path in valid_paths:
            return comment_path
        
        # Try to find files that end with the comment path
        for valid_path in valid_paths:
            if valid_path.endswith(comment_path):
                return valid_path
            
            # Also try matching just the filename
            comment_filename = comment_path.split('/')[-1]
            valid_filename = valid_path.split('/')[-1]
            if comment_filename == valid_filename:
                # Check if the path components match
                comment_parts = comment_path.split('/')
                valid_parts = valid_path.split('/')
                
                # If comment path's parts appear in order in valid path
                if self._path_parts_match(comment_parts, valid_parts):
                    return valid_path
        
        return None
    
    def _path_parts_match(self, short_parts: List[str], long_parts: List[str]) -> bool:
        """Check if short path parts appear in order in long path parts.
        
        Args:
            short_parts: Parts from shortened path
            long_parts: Parts from full path
            
        Returns:
            True if all short parts appear in order in long parts
        """
        if len(short_parts) > len(long_parts):
            return False
        
        # Try to find all short parts in order
        long_idx = 0
        for short_part in short_parts:
            found = False
            while long_idx < len(long_parts):
                if long_parts[long_idx] == short_part:
                    found = True
                    long_idx += 1
                    break
                long_idx += 1
            
            if not found:
                return False
        
        return True
    
    def get_authenticated_user(self) -> str:
        """Return the login name of the authenticated user (the bot)."""
        return self.github.get_user().login

    def get_bot_review_comments(self, pr_number: int) -> List[Dict]:
        """Get all existing inline review comments on a PR.

        Returns:
            List of dicts with path, line, body, user
        """
        try:
            pr = self.get_pr(pr_number)
            return [
                {
                    "path": c.path,
                    "line": getattr(c, "line", None) or getattr(c, "position", None) or 0,
                    "body": c.body,
                    "user": c.user.login,
                }
                for c in pr.get_review_comments()
            ]
        except GithubException as e:
            logger.warning(f"  ⚠ Could not fetch review comments: {e}")
            return []

    def get_existing_reviews(self, pr_number: int) -> List[Dict]:
        """Get existing reviews for a PR.
        
        Args:
            pr_number: PR number
            
        Returns:
            List of review dictionaries
        """
        logger.info(f"📝 Fetching existing reviews for PR #{pr_number}")
        
        try:
            pr = self.get_pr(pr_number)
            reviews = pr.get_reviews()
            
            review_list = []
            for review in reviews:
                review_list.append({
                    "id": review.id,
                    "user": review.user.login,
                    "state": review.state,
                    "body": review.body,
                    "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
                })
                logger.info(f"  {review.state} by {review.user.login}")
            
            logger.info(f"  Total: {len(review_list)} reviews")
            return review_list
            
        except GithubException as e:
            logger.error(f"  ❌ Error fetching reviews: {e}")
            raise
