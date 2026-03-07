"""Guide file loader for custom project rules."""
from pathlib import Path
from typing import List
import logging

logger = logging.getLogger(__name__)


class GuideLoader:
    """Load custom guide files from projects."""
    
    def load_guides(self, repo_path: str, guide_files: List[str]) -> str:
        """Load and combine guide files.

        Args:
            repo_path: Path to cloned repository
            guide_files: List of relative paths to guide files

        Returns:
            Combined guide content as string
        """
        guides = self.load_guides_dict(repo_path, guide_files)
        if not guides:
            return self._get_default_guide()
        combined = ""
        for guide_file, content in guides.items():
            combined += f"\n\n{'='*60}\n"
            combined += f"GUIDE FILE: {guide_file}\n"
            combined += f"{'='*60}\n\n"
            combined += content
        return combined

    def load_guides_dict(self, repo_path: str, guide_files: List[str]) -> dict:
        """Load guide files individually.

        Args:
            repo_path: Path to cloned repository
            guide_files: List of relative paths to guide files

        Returns:
            Dict mapping guide_file path -> content string
        """
        logger.info(f"📖 Loading guides from {repo_path}")
        guides = {}

        for guide_file in guide_files:
            path = Path(repo_path) / guide_file
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8")
                    guides[guide_file] = content
                    logger.info(f"  ✓ Loaded: {guide_file} ({len(content)} chars)")
                except Exception as e:
                    logger.warning(f"  ⚠ Error reading {guide_file}: {e}")
            else:
                logger.warning(f"  ⚠ Not found: {guide_file}")

        logger.info(f"  Total: {len(guides)} guides loaded")
        return guides
    
    def _get_default_guide(self) -> str:
        """Return default review guide when no custom guides found."""
        return """
# Default Code Review Guide

Review the code changes and provide feedback following these principles:

1. **Code Quality**: Check for clean, maintainable code
2. **Best Practices**: Ensure framework/language best practices are followed
3. **Security**: Look for potential security issues
4. **Performance**: Identify performance concerns
5. **Testing**: Verify adequate test coverage
6. **Documentation**: Check for necessary documentation

Return your review as JSON:
```json
{
  "event": "REQUEST_CHANGES" | "APPROVE" | "COMMENT",
  "summary": "Overall assessment in one paragraph",
  "comments": [
    {
      "path": "file/path.py",
      "line": 10,
      "body": "Your comment here"
    }
  ]
}
```
"""
