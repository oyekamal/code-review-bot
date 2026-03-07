# PR Review Bot - Multi-Project Architecture Proposal

## Executive Summary

This document proposes a refactored architecture for a scalable, multi-project code review automation system that supports Django, Next.js, React, and other frameworks.

---

## 🎯 Design Goals

1. **Multi-Project Support** - Review multiple repositories with different tech stacks
2. **Framework Extensibility** - Easy to add new languages/frameworks (Django, Next.js, Vue, Go, etc.)
3. **Configurable Review Rules** - Per-project, per-framework rules with inheritance
4. **Unified Tool** - Single system handling code review + test coverage analysis
5. **Maintainability** - Modular, testable, well-documented code
6. **Production-Ready** - Proper logging, error handling, metrics, monitoring

---

## 📁 Proposed Project Structure

```
pr-review-bot/
├── pyproject.toml              # Modern Python packaging (replaces setup.py)
├── README.md
├── .env.example                # Template for environment variables
├── docker-compose.yml          # Local development environment
├── Dockerfile
│
├── config/                     # All configuration files
│   ├── projects.yaml           # Multi-project configuration
│   ├── logging.yaml            # Structured logging config
│   └── rules/                  # Review rule definitions
│       ├── base/               # Common rules across all projects
│       │   ├── security.yaml
│       │   ├── performance.yaml
│       │   └── style.yaml
│       ├── django/             # Django-specific rules
│       │   ├── models.yaml
│       │   ├── views.yaml
│       │   ├── migrations.yaml
│       │   └── tests.yaml
│       ├── nextjs/             # Next.js-specific rules
│       │   ├── pages.yaml
│       │   ├── api.yaml
│       │   └── components.yaml
│       └── react/              # React-specific rules
│           ├── components.yaml
│           ├── hooks.yaml
│           └── state.yaml
│
├── guides/                     # Markdown guides for LLMs (current location)
│   ├── base/
│   │   └── GENERAL_REVIEW.md
│   ├── django/
│   │   ├── CODE_REVIEW.md
│   │   └── TEST_REVIEW.md
│   ├── nextjs/
│   │   └── CODE_REVIEW.md
│   └── react/
│       └── CODE_REVIEW.md
│
├── src/
│   └── pr_review_bot/
│       ├── __init__.py
│       ├── __main__.py         # Entry point: python -m pr_review_bot
│       │
│       ├── config/             # Configuration management
│       │   ├── __init__.py
│       │   ├── settings.py     # Centralized settings with Pydantic
│       │   ├── projects.py     # Project-specific config loader
│       │   └── rules.py        # Rule configuration loader
│       │
│       ├── core/               # Core business logic
│       │   ├── __init__.py
│       │   ├── orchestrator.py # Main review orchestration
│       │   ├── classifier.py   # PR classification (code/test/frontend/mixed)
│       │   ├── differ.py       # Diff processing and chunking
│       │   └── merger.py       # Result merging and deduplication
│       │
│       ├── integrations/       # External service integrations
│       │   ├── __init__.py
│       │   ├── github/
│       │   │   ├── __init__.py
│       │   │   ├── client.py   # GitHub API wrapper
│       │   │   ├── models.py   # GitHub data models (Pydantic)
│       │   │   └── webhooks.py # Webhook handling (future)
│       │   ├── llm/
│       │   │   ├── __init__.py
│       │   │   ├── base.py     # Abstract LLM interface
│       │   │   ├── ollama.py   # Ollama implementation
│       │   │   ├── anthropic.py# Claude implementation
│       │   │   └── openai.py   # OpenAI implementation (future)
│       │   └── vcs/            # Version control systems
│       │       ├── __init__.py
│       │       └── git.py      # Git operations
│       │
│       ├── reviewers/          # Framework-specific reviewers
│       │   ├── __init__.py
│       │   ├── base.py         # Abstract reviewer interface
│       │   ├── django_reviewer.py
│       │   ├── nextjs_reviewer.py
│       │   ├── react_reviewer.py
│       │   ├── python_reviewer.py  # Generic Python
│       │   └── typescript_reviewer.py  # Generic TypeScript
│       │
│       ├── analyzers/          # Specialized analysis modules
│       │   ├── __init__.py
│       │   ├── test_coverage.py    # Test coverage analysis
│       │   ├── security.py         # Security vulnerability scanning
│       │   ├── complexity.py       # Code complexity metrics
│       │   └── dependencies.py     # Dependency analysis
│       │
│       ├── models/             # Data models
│       │   ├── __init__.py
│       │   ├── pr.py           # PullRequest, File, Comment models
│       │   ├── review.py       # Review, ReviewComment, ReviewEvent
│       │   └── config.py       # Configuration models
│       │
│       ├── utils/              # Utilities
│       │   ├── __init__.py
│       │   ├── logging.py      # Structured logging
│       │   ├── retry.py        # Retry decorators
│       │   ├── cache.py        # Caching utilities
│       │   └── metrics.py      # Metrics collection
│       │
│       └── cli/                # Command-line interface
│           ├── __init__.py
│           ├── commands.py     # CLI commands (review, test, config)
│           └── server.py       # Webhook server (future)
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Pytest fixtures
│   ├── unit/                   # Unit tests
│   │   ├── test_classifier.py
│   │   ├── test_differ.py
│   │   └── test_config.py
│   ├── integration/            # Integration tests
│   │   ├── test_github.py
│   │   └── test_ollama.py
│   └── fixtures/               # Test data
│       ├── diffs/
│       └── responses/
│
├── scripts/                    # Utility scripts
│   ├── migrate_config.py       # Migrate old config to new format
│   ├── validate_rules.py       # Validate YAML rules
│   └── benchmark.py            # Performance benchmarking
│
└── docs/                       # Documentation
    ├── getting-started.md
    ├── configuration.md
    ├── adding-frameworks.md
    ├── deployment.md
    └── api.md
```

---

## 🔧 Key Components Explained

### 1. **Configuration Management (`config/`)**

**Multi-Project Configuration** (`config/projects.yaml`):
```yaml
projects:
  - name: taleemabad-core
    repo: Orenda-Project/taleemabad-core
    frameworks:
      - django
      - react
    llm:
      provider: ollama
      model: llama3.2
    rules:
      - base/security
      - base/performance
      - django/models
      - django/migrations
      - react/components
    review:
      max_comments: 8
      auto_approve_on_resolution: true
    
  - name: ecommerce-nextjs
    repo: myorg/ecommerce-platform
    frameworks:
      - nextjs
      - typescript
    llm:
      provider: anthropic
      model: claude-sonnet-4
    rules:
      - base/security
      - nextjs/pages
      - nextjs/api
      - typescript/types
    review:
      max_comments: 10
      auto_approve_on_resolution: false

  - name: inventory-django
    repo: myorg/inventory-system
    frameworks:
      - django
    llm:
      provider: ollama
      model: llama3.2
    rules:
      - base/security
      - django/models
      - django/views
```

**Settings with Pydantic** (`config/settings.py`):
```python
from pydantic import BaseModel, Field, validator
from typing import Literal, Optional

class LLMConfig(BaseModel):
    provider: Literal["ollama", "anthropic", "openai"]
    model: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout: int = 120
    temperature: float = 0.1

class ProjectConfig(BaseModel):
    name: str
    repo: str
    frameworks: list[str]
    llm: LLMConfig
    rules: list[str]
    review_settings: dict

class Settings(BaseModel):
    github_token: str = Field(..., env="GITHUB_TOKEN")
    bot_username: str = Field(..., env="BOT_USERNAME")
    projects: list[ProjectConfig]
    log_level: str = "INFO"
    
    @validator("github_token")
    def validate_token(cls, v):
        if not v.startswith("ghp_"):
            raise ValueError("Invalid GitHub token format")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

---

### 2. **Framework-Agnostic Reviewer Interface**

```python
# src/pr_review_bot/reviewers/base.py
from abc import ABC, abstractmethod
from typing import List, Optional
from ..models.pr import PullRequest, File
from ..models.review import Review

class BaseReviewer(ABC):
    """Abstract base class for framework-specific reviewers."""
    
    def __init__(self, project_config: ProjectConfig, llm_client: BaseLLM):
        self.config = project_config
        self.llm = llm_client
        self.rules = self._load_rules()
        self.guide = self._load_guide()
    
    @abstractmethod
    def can_review(self, file: File) -> bool:
        """Check if this reviewer can handle the given file."""
        pass
    
    @abstractmethod
    def classify_pr(self, files: List[File]) -> str:
        """Classify PR type (code, test, mixed, etc.)."""
        pass
    
    @abstractmethod
    def _load_rules(self) -> List[Rule]:
        """Load framework-specific rules."""
        pass
    
    @abstractmethod
    def _load_guide(self) -> str:
        """Load framework-specific review guide."""
        pass
    
    def review(self, pr: PullRequest) -> Review:
        """Main review method - delegates to framework-specific implementation."""
        files = self._filter_reviewable_files(pr.files)
        pr_type = self.classify_pr(files)
        guide = self._get_guide_for_pr_type(pr_type)
        chunks = self._create_diff_chunks(files)
        
        results = []
        for chunk in chunks:
            result = self.llm.review(guide, chunk)
            results.append(result)
        
        return self._merge_results(results)


# src/pr_review_bot/reviewers/django_reviewer.py
class DjangoReviewer(BaseReviewer):
    """Django-specific code reviewer."""
    
    def can_review(self, file: File) -> bool:
        patterns = [
            "*/models.py",
            "*/views.py",
            "*/serializers.py",
            "*/migrations/*.py",
            "*/tests/*.py"
        ]
        return any(fnmatch.fnmatch(file.path, pattern) for pattern in patterns)
    
    def classify_pr(self, files: List[File]) -> str:
        # Django-specific classification logic
        test_files = [f for f in files if "/tests/" in f.path]
        migration_files = [f for f in files if "/migrations/" in f.path]
        
        if len(migration_files) > len(files) / 2:
            return "migration-heavy"
        if len(test_files) > len(files) / 2:
            return "test"
        return "code"


# src/pr_review_bot/reviewers/nextjs_reviewer.py
class NextJSReviewer(BaseReviewer):
    """Next.js-specific code reviewer."""
    
    def can_review(self, file: File) -> bool:
        patterns = [
            "app/**/*.tsx",
            "app/**/*.ts",
            "pages/**/*.tsx",
            "components/**/*.tsx",
            "lib/**/*.ts"
        ]
        return any(fnmatch.fnmatch(file.path, pattern) for pattern in patterns)
    
    def classify_pr(self, files: List[File]) -> str:
        api_files = [f for f in files if "/api/" in f.path]
        page_files = [f for f in files if "/pages/" in f.path or "/app/" in f.path]
        component_files = [f for f in files if "/components/" in f.path]
        
        if len(api_files) > 0:
            return "api"
        if len(page_files) > 0:
            return "pages"
        if len(component_files) > 0:
            return "components"
        return "mixed"
```

---

### 3. **Orchestrator - Multi-Project Coordination**

```python
# src/pr_review_bot/core/orchestrator.py
class ReviewOrchestrator:
    """Coordinates reviews across multiple projects and frameworks."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.github_clients = {}
        self.llm_clients = {}
        self.reviewers = {}
        
        self._initialize_clients()
        self._initialize_reviewers()
    
    def _initialize_clients(self):
        """Initialize GitHub and LLM clients for each project."""
        for project in self.settings.projects:
            # GitHub client
            self.github_clients[project.name] = GitHubClient(
                token=self.settings.github_token,
                repo=project.repo
            )
            
            # LLM client
            self.llm_clients[project.name] = self._create_llm_client(project.llm)
    
    def _initialize_reviewers(self):
        """Initialize framework-specific reviewers."""
        reviewer_map = {
            "django": DjangoReviewer,
            "nextjs": NextJSReviewer,
            "react": ReactReviewer,
            "python": PythonReviewer,
            "typescript": TypeScriptReviewer,
        }
        
        for project in self.settings.projects:
            project_reviewers = []
            for framework in project.frameworks:
                reviewer_class = reviewer_map.get(framework)
                if reviewer_class:
                    reviewer = reviewer_class(
                        project_config=project,
                        llm_client=self.llm_clients[project.name]
                    )
                    project_reviewers.append(reviewer)
            self.reviewers[project.name] = project_reviewers
    
    def review_all_projects(self):
        """Review all open PRs across all configured projects."""
        for project in self.settings.projects:
            logger.info(f"Starting review for project: {project.name}")
            self.review_project(project.name)
    
    def review_project(self, project_name: str):
        """Review all open PRs for a specific project."""
        github = self.github_clients[project_name]
        reviewers = self.reviewers[project_name]
        
        prs = github.list_open_prs()
        for pr in prs:
            self.review_pr(project_name, pr)
    
    def review_pr(self, project_name: str, pr: PullRequest):
        """Review a single PR using appropriate framework reviewers."""
        github = self.github_clients[project_name]
        
        # Check if bot has already reviewed
        bot_state = github.get_bot_review_state(pr.number)
        if self._should_skip_pr(bot_state):
            return
        
        # Fetch PR files
        files = github.get_pr_files(pr.number)
        
        # Route files to appropriate reviewers
        reviews = []
        for reviewer in self.reviewers[project_name]:
            reviewable_files = [f for f in files if reviewer.can_review(f)]
            if reviewable_files:
                pr_with_files = PullRequest(
                    number=pr.number,
                    title=pr.title,
                    files=reviewable_files
                )
                review = reviewer.review(pr_with_files)
                reviews.append(review)
        
        # Merge and post review
        merged_review = self._merge_reviews(reviews)
        github.post_review(pr.number, merged_review)
```

---

### 4. **LLM Provider Abstraction**

```python
# src/pr_review_bot/integrations/llm/base.py
class BaseLLM(ABC):
    """Abstract interface for LLM providers."""
    
    @abstractmethod
    def review(self, guide: str, diff: str) -> dict:
        """Send diff to LLM and return parsed review result."""
        pass


# src/pr_review_bot/integrations/llm/ollama.py
class OllamaLLM(BaseLLM):
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model
    
    def review(self, guide: str, diff: str) -> dict:
        # Existing Ollama implementation
        pass


# src/pr_review_bot/integrations/llm/anthropic.py
class AnthropicLLM(BaseLLM):
    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
    
    def review(self, guide: str, diff: str) -> dict:
        # Claude implementation
        pass
```

---

### 5. **Unified Test Coverage Analysis**

```python
# src/pr_review_bot/analyzers/test_coverage.py
class TestCoverageAnalyzer:
    """Analyzes test coverage across different frameworks."""
    
    def __init__(self, llm_client: BaseLLM, framework: str):
        self.llm = llm_client
        self.framework = framework
        self.strategy = self._get_strategy()
    
    def _get_strategy(self):
        strategies = {
            "django": DjangoTestStrategy(),
            "nextjs": NextJSTestStrategy(),
            "react": ReactTestStrategy(),
        }
        return strategies.get(self.framework)
    
    def analyze(self, pr: PullRequest) -> TestCoverageReport:
        """Analyze test coverage for the PR."""
        source_files, test_files = self.strategy.classify_files(pr.files)
        
        untested_files = []
        for source_file in source_files:
            if not self._has_corresponding_tests(source_file, test_files):
                untested_files.append(source_file)
        
        if not untested_files:
            return TestCoverageReport(status="complete", files=[])
        
        # Use LLM to generate test suggestions
        suggestions = []
        for file in untested_files[:5]:  # Limit to 5 to control costs
            diff = self._get_diff(file)
            suggestion = self.llm.suggest_tests(diff)
            suggestions.append(suggestion)
        
        return TestCoverageReport(
            status="incomplete",
            untested_files=untested_files,
            suggestions=suggestions
        )
```

---

## 🚀 Migration Strategy

### Phase 1: Foundation (Week 1)
1. Create new project structure
2. Set up `pyproject.toml` with dependencies
3. Implement configuration system (Pydantic models)
4. Create base abstractions (BaseReviewer, BaseLLM)

### Phase 2: Core Refactoring (Week 2)
1. Extract GitHub client from monolithic script
2. Extract Ollama client
3. Implement orchestrator
4. Port Django reviewer logic

### Phase 3: Testing & Polish (Week 3)
1. Write unit tests for all core components
2. Write integration tests
3. Add comprehensive logging
4. Create Docker setup for local development

### Phase 4: Expand Frameworks (Week 4+)
1. Implement Next.js reviewer
2. Implement React reviewer
3. Add multi-project configuration
4. Deploy and monitor

---

## 📊 Benefits of This Architecture

### 1. **Scalability**
- ✅ Add new projects by editing YAML config (no code changes)
- ✅ Add new frameworks by implementing `BaseReviewer` interface
- ✅ Swap LLM providers without touching reviewer logic

### 2. **Maintainability**
- ✅ Each component has single responsibility
- ✅ Easy to locate and fix bugs
- ✅ Comprehensive test coverage possible
- ✅ Clear separation between business logic and integrations

### 3. **Extensibility**
- ✅ Plugin architecture for reviewers
- ✅ Rule-based configuration inheritance
- ✅ Custom analyzers (security, complexity, etc.)

### 4. **Developer Experience**
- ✅ CLI for manual testing: `pr-review-bot review --project taleemabad --pr 123`
- ✅ Docker Compose for local development
- ✅ Comprehensive documentation
- ✅ Type hints for IDE support

### 5. **Observability**
- ✅ Structured logging (JSON format)
- ✅ Metrics collection (review time, LLM costs, etc.)
- ✅ Error tracking integration (Sentry, etc.)

---

## 🔐 Security Improvements

1. **Secret Management**: Use environment variables or secret managers, never hardcode
2. **Token Scoping**: Create separate GitHub tokens per project with minimal permissions
3. **Input Validation**: Pydantic models validate all configuration
4. **Rate Limiting**: Built into GitHub and LLM clients with exponential backoff
5. **Audit Logging**: All review actions logged with metadata

---

## 📈 Performance Optimizations

1. **Caching**: Cache LLM responses for identical diffs
2. **Parallel Processing**: Review multiple PRs in parallel (thread pool)
3. **Smart Chunking**: Adaptive chunk sizing based on LLM context window
4. **Incremental Reviews**: Only review changed files since last review

---

## 🧪 Testing Strategy

1. **Unit Tests**: All core logic (classifier, differ, merger, config)
2. **Integration Tests**: GitHub API, LLM providers
3. **End-to-End Tests**: Full review workflow with mocked LLM
4. **Fixtures**: Real PR diffs for regression testing

---

## 📝 Documentation Requirements

1. **Getting Started**: Setup for new team members
2. **Configuration Guide**: Explain YAML configs, rule inheritance
3. **Adding Frameworks**: Step-by-step guide with template
4. **Deployment**: Docker, cron, GitHub Actions, webhook options
5. **Troubleshooting**: Common issues and solutions

---

## 🛠️ Technology Stack

- **Python 3.11+**: Modern Python features
- **Pydantic**: Configuration and data validation
- **Click**: CLI framework
- **Structlog**: Structured logging
- **Pytest**: Testing framework
- **Docker**: Containerization
- **GitHub Actions**: CI/CD (optional)
- **FastAPI**: Webhook server (future)

---

## 💡 Next Steps

1. **Review this proposal** and provide feedback
2. **Prioritize features** - What's most critical for your use case?
3. **Create migration plan** - Can you pause reviews during refactor?
4. **Set up repo** - New structure in a branch or separate repo?
5. **Start with Phase 1** - Foundation work is framework-agnostic

---

## ❓ Questions to Answer

1. Do you need webhook support (real-time reviews) or is cron sufficient?
2. Which frameworks are highest priority? Django + Next.js?
3. Do you want to keep using Ollama or switch to Claude/GPT?
4. What's your deployment environment? (server, cloud, GitHub Actions)
5. Do you need a web UI for configuration or is YAML acceptable?

---

**This architecture will transform your bot from a single-project script into a production-grade, multi-project code review platform.**
