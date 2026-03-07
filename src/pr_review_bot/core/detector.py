"""Framework auto-detection."""
from pathlib import Path
from typing import List, Dict, Set
import logging

logger = logging.getLogger(__name__)


class FrameworkDetector:
    """Auto-detect frameworks from codebase structure."""
    
    DETECTION_RULES = {
        "django": {
            "files": ["manage.py"],
            "patterns": ["**/models.py", "**/views.py", "**/settings.py"],
            "packages": ["django", "djangorestframework"],
        },
        "nextjs": {
            "files": ["next.config.js", "next.config.ts", "next.config.mjs"],
            "patterns": ["app/**/page.tsx", "pages/**/*.tsx", "pages/**/*.jsx"],
            "packages": ["next"],
        },
        "react": {
            "files": ["package.json"],
            "patterns": ["src/**/*.jsx", "src/**/*.tsx"],
            "packages": ["react"],
        },
        "fastapi": {
            "patterns": ["**/main.py"],
            "packages": ["fastapi", "uvicorn"],
        },
        "flask": {
            "patterns": ["**/app.py", "**/application.py"],
            "packages": ["flask"],
        },
    }
    
    def detect(self, repo_path: str) -> List[str]:
        """Scan repo and return detected frameworks.
        
        Args:
            repo_path: Path to cloned repository
            
        Returns:
            List of detected framework names
        """
        logger.info(f"🔍 Detecting frameworks in {repo_path}")
        detected: Set[str] = set()
        
        for framework, rules in self.DETECTION_RULES.items():
            if self._check_framework(repo_path, framework, rules):
                detected.add(framework)
                logger.info(f"  ✓ Detected: {framework}")
        
        if not detected:
            logger.warning("  ⚠ No frameworks detected")
        
        return sorted(list(detected))
    
    def _check_framework(self, repo_path: str, framework: str, rules: Dict) -> bool:
        """Check if a framework is present based on rules."""
        # Check for specific files
        for filename in rules.get("files", []):
            if self._file_exists(repo_path, filename):
                logger.debug(f"  Found {filename} for {framework}")
                return True
        
        # Check for file patterns
        for pattern in rules.get("patterns", []):
            if self._pattern_exists(repo_path, pattern):
                logger.debug(f"  Found pattern {pattern} for {framework}")
                return True
        
        # Check package files
        if self._check_packages(repo_path, rules.get("packages", [])):
            logger.debug(f"  Found package dependencies for {framework}")
            return True
        
        return False
    
    def _file_exists(self, repo_path: str, filename: str) -> bool:
        """Check if a specific file exists in repo."""
        try:
            # Check root first
            root_file = Path(repo_path) / filename
            if root_file.exists():
                return True
            
            # Then recursively search
            matches = list(Path(repo_path).rglob(filename))
            return len(matches) > 0
        except Exception as e:
            logger.debug(f"  Error checking file {filename}: {e}")
            return False
    
    def _pattern_exists(self, repo_path: str, pattern: str) -> bool:
        """Check if files matching pattern exist."""
        try:
            matches = list(Path(repo_path).rglob(pattern))
            return len(matches) > 0
        except Exception as e:
            logger.debug(f"  Error checking pattern {pattern}: {e}")
            return False
    
    def _check_packages(self, repo_path: str, packages: List[str]) -> bool:
        """Check if packages are in requirements/package.json."""
        if not packages:
            return False
        
        # Check requirements.txt (Python)
        req_file = Path(repo_path) / "requirements.txt"
        if req_file.exists():
            content = req_file.read_text()
            if any(pkg in content for pkg in packages):
                return True
        
        # Check package.json (Node)
        pkg_file = Path(repo_path) / "package.json"
        if pkg_file.exists():
            content = pkg_file.read_text()
            if any(f'"{pkg}"' in content for pkg in packages):
                return True
        
        return False
