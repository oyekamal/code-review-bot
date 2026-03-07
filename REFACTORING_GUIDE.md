# Refactoring Guide - From Monolith to Modular Architecture

This guide provides detailed, actionable steps to refactor your existing PR review bot into the proposed architecture.

---

## 🎯 Current Problems & Solutions

### Problem 1: 982-Line Monolithic File

**Current:**
```python
# scripts/pr_review_bot.py - Everything in one file
# - Config (lines 23-37)
# - GitHub API (lines 49-180)
# - PR classification (lines 237-320)
# - Ollama integration (lines 475-600)
# - Review posting (lines 720-850)
# - Main orchestration (lines 900-982)
```

**Solution: Split into focused modules**

```
src/pr_review_bot/
├── config/settings.py          # Lines 23-37 → Pydantic models
├── integrations/github/client.py  # Lines 49-180 → GitHub class
├── core/classifier.py          # Lines 237-320 → Classifier class
├── integrations/llm/ollama.py  # Lines 475-600 → Ollama class
├── core/reviewer.py            # Lines 720-850 → Reviewer class
└── __main__.py                 # Lines 900-982 → CLI entry point
```

---

### Problem 2: Hardcoded Configuration

**Current:**
```python
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "Orenda-Project/taleemabad-core")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "oyekamal")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
```

**New: Pydantic with Validation**

```python
# src/pr_review_bot/config/settings.py
from pydantic import BaseModel, Field, HttpUrl, validator
from pydantic_settings import BaseSettings
from typing import Optional

class LLMConfig(BaseModel):
    """LLM provider configuration."""
    provider: str = "ollama"
    model: str = "llama3.2"
    base_url: HttpUrl = "http://localhost:11434"
    api_key: Optional[str] = None
    timeout: int = 120
    temperature: float = 0.1
    max_tokens: int = 1024

class ReviewConfig(BaseModel):
    """Review behavior configuration."""
    max_comments: int = Field(8, ge=1, le=20)
    max_diff_chars: int = Field(8000, ge=1000, le=50000)
    auto_approve_on_resolution: bool = True
    skip_draft_prs: bool = True
    required_label: Optional[str] = "ready-for-CI"

class ProjectSettings(BaseModel):
    """Per-project configuration."""
    name: str
    repo: str = Field(..., regex=r"^[\w-]+/[\w-]+$")
    frameworks: list[str] = ["django"]
    llm: LLMConfig = LLMConfig()
    review: ReviewConfig = ReviewConfig()
    guides_dir: Optional[str] = None
    
    @validator("frameworks")
    def validate_frameworks(cls, v):
        supported = {"django", "nextjs", "react", "vue", "python", "typescript"}
        invalid = set(v) - supported
        if invalid:
            raise ValueError(f"Unsupported frameworks: {invalid}")
        return v

class Settings(BaseSettings):
    """Global application settings."""
    github_token: str = Field(..., env="GITHUB_TOKEN")
    bot_username: str = Field(..., env="BOT_USERNAME")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    projects: list[ProjectSettings] = []
    
    @validator("github_token")
    def validate_github_token(cls, v):
        if not v:
            raise ValueError("GITHUB_TOKEN is required")
        if not v.startswith(("ghp_", "ghs_", "github_pat_")):
            raise ValueError("Invalid GitHub token format")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Usage
settings = Settings()
```

---

### Problem 3: No Multi-Project Support

**Current:** Single repo hardcoded
```python
GITHUB_REPO = os.environ.get("GITHUB_REPO", "Orenda-Project/taleemabad-core")
```

**New: YAML Configuration**

```yaml
# config/projects.yaml
projects:
  - name: taleemabad-core
    repo: Orenda-Project/taleemabad-core
    frameworks:
      - django
      - react
    llm:
      provider: ollama
      model: llama3.2
      base_url: http://localhost:11434
    review:
      max_comments: 8
      auto_approve_on_resolution: true
    guides_dir: ./guides/django
  
  - name: ecommerce-platform
    repo: myorg/ecommerce-nextjs
    frameworks:
      - nextjs
      - typescript
    llm:
      provider: anthropic
      model: claude-sonnet-4
      api_key: ${ANTHROPIC_API_KEY}  # References env var
    review:
      max_comments: 10
      auto_approve_on_resolution: false
    guides_dir: ./guides/nextjs
  
  - name: inventory-api
    repo: myorg/inventory-django
    frameworks:
      - django
    llm:
      provider: ollama
      model: llama3.2
    review:
      max_comments: 8
```

**Loading Configuration:**
```python
# src/pr_review_bot/config/loader.py
import yaml
from pathlib import Path
from .settings import Settings, ProjectSettings

def load_config(config_path: str = "config/projects.yaml") -> Settings:
    """Load configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    
    with open(path) as f:
        data = yaml.safe_load(f)
    
    # Expand environment variables in config
    data = _expand_env_vars(data)
    
    # Create Settings object with validation
    projects = [ProjectSettings(**p) for p in data["projects"]]
    settings = Settings(projects=projects)
    
    return settings

def _expand_env_vars(data: dict) -> dict:
    """Recursively expand ${VAR} references to environment variables."""
    import os
    import re
    
    def expand(value):
        if isinstance(value, str):
            # Replace ${VAR} with os.environ["VAR"]
            pattern = r'\$\{(\w+)\}'
            matches = re.findall(pattern, value)
            for var in matches:
                env_value = os.environ.get(var, "")
                value = value.replace(f"${{{var}}}", env_value)
        elif isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [expand(item) for item in value]
        return value
    
    return expand(data)
```

---

### Problem 4: Tight Coupling Between Components

**Current:** Direct function calls everywhere
```python
def main():
    prs = list_open_prs()  # Directly calls GitHub
    for pr in prs:
        files = get_pr_files(pr["number"])  # Calls GitHub again
        pr_type = classify_pr(files)  # Inline logic
        result = call_ollama(guide, diff)  # Direct Ollama call
        post_review(pr, result)  # Direct GitHub call
```

**New: Dependency Injection & Interfaces**

```python
# src/pr_review_bot/integrations/github/client.py
from typing import Protocol, List
from ...models.pr import PullRequest, File

class GitHubClient:
    """GitHub API client with proper error handling."""
    
    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo
        self.base_url = "https://api.github.com"
        self._session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        return session
    
    @retry_on_rate_limit(max_retries=3)
    def list_open_prs(self) -> List[PullRequest]:
        """Fetch all open PRs for the repository."""
        prs = []
        page = 1
        
        while True:
            response = self._session.get(
                f"{self.base_url}/repos/{self.repo}/pulls",
                params={"state": "open", "per_page": 100, "page": page},
                timeout=30
            )
            response.raise_for_status()
            
            batch = response.json()
            if not batch:
                break
            
            prs.extend([PullRequest.from_github(pr) for pr in batch])
            
            if len(batch) < 100:
                break
            page += 1
        
        return prs


# src/pr_review_bot/integrations/llm/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any

class LLMProvider(ABC):
    """Abstract interface for LLM providers."""
    
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt."""
        pass
    
    @abstractmethod
    def review_code(self, guide: str, diff: str) -> Dict[str, Any]:
        """Review code diff using guide and return structured result."""
        pass


# src/pr_review_bot/core/orchestrator.py
class ReviewOrchestrator:
    """Coordinates the review process with injected dependencies."""
    
    def __init__(
        self,
        github_client: GitHubClient,
        llm_provider: LLMProvider,
        classifier: PRClassifier,
        config: ProjectSettings
    ):
        self.github = github_client
        self.llm = llm_provider
        self.classifier = classifier
        self.config = config
    
    def review_all_prs(self):
        """Main entry point - review all open PRs."""
        prs = self.github.list_open_prs()
        
        for pr in prs:
            try:
                self.review_pr(pr)
            except Exception as e:
                logger.error(f"Failed to review PR #{pr.number}", exc_info=True)
    
    def review_pr(self, pr: PullRequest):
        """Review a single PR."""
        # Check if should skip
        if self._should_skip(pr):
            return
        
        # Fetch files
        files = self.github.get_pr_files(pr.number)
        pr.files = files
        
        # Classify PR
        pr_type = self.classifier.classify(files)
        
        # Load appropriate guide
        guide = self._load_guide(pr_type)
        
        # Create diff chunks
        chunks = self._create_chunks(files)
        
        # Review each chunk
        results = []
        for chunk in chunks:
            result = self.llm.review_code(guide, chunk.diff)
            results.append(result)
        
        # Merge and post
        merged = self._merge_results(results)
        self.github.post_review(pr.number, merged)
```

---

### Problem 5: No Testing Strategy

**Current:** No tests at all

**New: Comprehensive Test Suite**

```python
# tests/unit/test_classifier.py
import pytest
from pr_review_bot.core.classifier import PRClassifier
from pr_review_bot.models.pr import File

class TestPRClassifier:
    """Test PR classification logic."""
    
    @pytest.fixture
    def classifier(self):
        return PRClassifier(framework="django")
    
    def test_classify_test_pr(self, classifier):
        """Test PR with >50% test files should be classified as 'test'."""
        files = [
            File(path="app/tests/test_views.py", additions=50, deletions=10),
            File(path="app/tests/test_models.py", additions=30, deletions=5),
            File(path="app/models.py", additions=10, deletions=2),
        ]
        
        result = classifier.classify(files)
        
        assert result == "test"
    
    def test_classify_migration_pr(self, classifier):
        """PRs with mostly migrations should be classified correctly."""
        files = [
            File(path="app/migrations/0023_add_field.py", additions=100, deletions=0),
            File(path="app/migrations/0024_remove_field.py", additions=50, deletions=0),
            File(path="app/models.py", additions=5, deletions=0),
        ]
        
        result = classifier.classify(files)
        
        assert result == "migration-heavy"


# tests/integration/test_github_client.py
import pytest
from pr_review_bot.integrations.github.client import GitHubClient
from unittest.mock import Mock, patch

class TestGitHubClient:
    """Integration tests for GitHub API client."""
    
    @pytest.fixture
    def client(self):
        return GitHubClient(token="ghp_test", repo="owner/repo")
    
    @patch("requests.Session.get")
    def test_list_open_prs(self, mock_get, client):
        """Test fetching open PRs from GitHub API."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"number": 123, "title": "Test PR", "draft": False}
        ]
        mock_get.return_value = mock_response
        
        prs = client.list_open_prs()
        
        assert len(prs) == 1
        assert prs[0].number == 123
        assert prs[0].title == "Test PR"
    
    @patch("requests.Session.get")
    def test_rate_limit_retry(self, mock_get, client):
        """Test that rate limit errors trigger retry."""
        # First call returns rate limit error
        mock_response_error = Mock()
        mock_response_error.status_code = 403
        mock_response_error.text = "rate limit exceeded"
        
        # Second call succeeds
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = []
        
        mock_get.side_effect = [mock_response_error, mock_response_success]
        
        prs = client.list_open_prs()
        
        assert mock_get.call_count == 2
        assert prs == []


# tests/fixtures/sample_diffs.py
DJANGO_MODEL_VIOLATION = """
--- a/app/models.py
+++ b/app/models.py
@@ -10,7 +10,7 @@ from django.db import models
+class School(models.Model):  # Missing SoftDeleteAuditableMixin
+    name = models.CharField(max_length=100)
+    is_active = models.BooleanField(default=True)
"""

DJANGO_HARD_DELETE = """
--- a/app/views.py
+++ b/app/views.py
@@ -20,3 +20,4 @@ def delete_school(request, school_id):
+    school = School.objects.get(id=school_id)
+    school.delete()  # VIOLATION: Hard delete
+    return Response(status=204)
"""
```

---

## 🔄 Step-by-Step Migration Plan

### Step 1: Create New Structure (No Breaking Changes)

```bash
# Create new structure alongside existing scripts
mkdir -p src/pr_review_bot/{config,core,integrations,models,utils}
mkdir -p tests/{unit,integration,fixtures}
mkdir -p config/rules/{base,django,nextjs,react}

# Initialize Python package
touch src/pr_review_bot/__init__.py
touch src/pr_review_bot/{config,core,integrations,models,utils}/__init__.py
```

### Step 2: Extract Configuration

```python
# src/pr_review_bot/config/settings.py
# Copy lines 23-37 from pr_review_bot.py and convert to Pydantic models
# (See detailed example above)
```

### Step 3: Extract GitHub Client

```python
# src/pr_review_bot/integrations/github/client.py
# Copy lines 49-180 from pr_review_bot.py
# Wrap in GitHubClient class with proper methods
# Add retry decorators, error handling

class GitHubClient:
    def __init__(self, token: str, repo: str):
        # Copy _github_headers logic
        pass
    
    def list_open_prs(self) -> List[PullRequest]:
        # Copy list_open_prs function
        pass
    
    def get_pr_files(self, pr_number: int) -> List[File]:
        # Copy get_pr_files function
        pass
    
    # ... etc for all GitHub operations
```

### Step 4: Extract Classifier

```python
# src/pr_review_bot/core/classifier.py
# Copy lines 237-320 from pr_review_bot.py

class PRClassifier:
    def __init__(self, framework: str = "django"):
        self.framework = framework
    
    def classify(self, files: List[File]) -> str:
        # Copy classify_pr logic
        # Add framework-specific classification
        pass
    
    def _is_reviewable(self, filename: str) -> bool:
        # Copy _is_reviewable logic
        pass
    
    def _is_test_file(self, filename: str) -> bool:
        # Copy _is_test_file logic
        pass
```

### Step 5: Extract LLM Provider

```python
# src/pr_review_bot/integrations/llm/ollama.py
# Copy lines 475-600 from pr_review_bot.py

class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model
    
    def review_code(self, guide: str, diff: str) -> dict:
        # Copy call_ollama logic
        pass
    
    def _parse_response(self, raw: str) -> dict:
        # Copy _parse_ollama_json logic
        pass
```

### Step 6: Create Orchestrator

```python
# src/pr_review_bot/core/orchestrator.py
# This is NEW - combines all the pieces

class ReviewOrchestrator:
    def __init__(self, config: Settings):
        self.config = config
        self.github = GitHubClient(config.github_token, config.repo)
        self.llm = self._create_llm_provider()
        self.classifier = PRClassifier()
    
    def review_all_prs(self):
        # Copy main() logic from pr_review_bot.py lines 900-982
        prs = self.github.list_open_prs()
        for pr in prs:
            self.review_pr(pr)
    
    def review_pr(self, pr: PullRequest):
        # Copy review_pr logic
        pass
```

### Step 7: Create CLI Entry Point

```python
# src/pr_review_bot/__main__.py
import click
from .config.loader import load_config
from .core.orchestrator import ReviewOrchestrator

@click.group()
def cli():
    """PR Review Bot - Automated code review across multiple projects."""
    pass

@cli.command()
@click.option("--config", default="config/projects.yaml", help="Config file path")
@click.option("--project", help="Review specific project only")
@click.option("--pr", type=int, help="Review specific PR number")
def review(config, project, pr):
    """Run code review for configured projects."""
    settings = load_config(config)
    orchestrator = ReviewOrchestrator(settings)
    
    if project and pr:
        orchestrator.review_specific_pr(project, pr)
    elif project:
        orchestrator.review_project(project)
    else:
        orchestrator.review_all_projects()

@cli.command()
@click.option("--config", default="config/projects.yaml")
def validate(config):
    """Validate configuration file."""
    try:
        settings = load_config(config)
        click.echo(f"✓ Configuration valid: {len(settings.projects)} projects")
        for project in settings.projects:
            click.echo(f"  - {project.name} ({project.repo})")
    except Exception as e:
        click.echo(f"✗ Configuration invalid: {e}", err=True)
        raise click.Abort()

if __name__ == "__main__":
    cli()
```

### Step 8: Update pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "pr-review-bot"
version = "2.0.0"
description = "Multi-project automated PR code review system"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "click>=8.1.0",
    "pyyaml>=6.0",
    "anthropic>=0.18.0",
    "structlog>=23.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-mock>=3.12.0",
    "black>=23.12.0",
    "ruff>=0.1.9",
    "mypy>=1.8.0",
]

[project.scripts]
pr-review-bot = "pr_review_bot.__main__:cli"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
addopts = "--cov=src/pr_review_bot --cov-report=html --cov-report=term"

[tool.black]
line-length = 100
target-version = ["py311"]

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "UP", "B", "A", "C4", "PT"]
ignore = ["E501"]  # Line too long (handled by black)
```

### Step 9: Parallel Testing (Keep Old Script Running)

```bash
# Install new package in development mode
pip install -e .

# Test new CLI while old cron job still runs
pr-review-bot review --project taleemabad-core --pr 123

# Once validated, update cron job:
# OLD: python3 /path/scripts/pr_review_bot.py
# NEW: pr-review-bot review --config /path/config/projects.yaml
```

---

## 🧪 Testing the Refactored Code

### Run Unit Tests
```bash
pytest tests/unit/ -v
```

### Run Integration Tests (with mocks)
```bash
pytest tests/integration/ -v
```

### Test Configuration Loading
```bash
pr-review-bot validate --config config/projects.yaml
```

### Manual PR Review
```bash
# Review specific PR
pr-review-bot review --project taleemabad-core --pr 456

# Review all PRs for one project
pr-review-bot review --project taleemabad-core

# Review all projects
pr-review-bot review
```

---

## 📊 Comparison: Before vs After

| Aspect | Before | After |
|--------|--------|-------|
| **Lines of Code** | 982 lines (single file) | ~200 lines per module (6 modules) |
| **Configuration** | Environment variables only | YAML + Pydantic validation |
| **Projects Supported** | 1 (hardcoded) | Unlimited (config-driven) |
| **Frameworks** | Django only | Django, Next.js, React, extensible |
| **Testing** | None | 80%+ coverage |
| **LLM Providers** | Ollama only | Ollama, Claude, OpenAI |
| **Deployment** | Cron script | CLI, Docker, webhooks |
| **Maintainability** | Low (monolith) | High (modular) |
| **Extensibility** | Hard (requires code changes) | Easy (config + plugin) |

---

## 🚀 Rollout Strategy

### Week 1: Infrastructure
- [ ] Create new folder structure
- [ ] Set up pyproject.toml
- [ ] Write configuration loader
- [ ] Test configuration validation

### Week 2: Core Refactoring
- [ ] Extract GitHub client
- [ ] Extract LLM providers
- [ ] Extract classifier
- [ ] Write unit tests for each

### Week 3: Integration
- [ ] Build orchestrator
- [ ] Create CLI
- [ ] Add logging
- [ ] Test end-to-end locally

### Week 4: Deployment
- [ ] Run both old and new in parallel
- [ ] Monitor for differences
- [ ] Switch cron to new system
- [ ] Deprecate old scripts

---

## ✅ Success Criteria

- [ ] All existing functionality preserved
- [ ] Can review PRs for taleemabad-core (Django)
- [ ] Can add new projects via YAML config
- [ ] Test coverage > 80%
- [ ] Documentation complete
- [ ] Deploy successfully to production
- [ ] No regressions in review quality

---

**This refactoring transforms your bot from a one-off script into a professional, scalable code review platform ready for your entire organization.**
