# Smart Project Discovery & Custom Guide System

## Overview

This guide describes how the PR review bot **automatically learns** about new codebases without requiring manual framework configuration, and how to use project-specific guide files like `claude.md` for custom rules.

---

## 🎯 Your Workflow Requirements

1. **Add new project easily** - Just add repo URL to config
2. **Bot analyzes codebase** - Auto-detects frameworks, patterns, conventions
3. **Custom guide files** - Projects can have `.github/claude.md` with specific rules
4. **Generate improvements** - Bot writes structured improvement suggestions
5. **Test with Ollama first** - Free local testing, switch to Claude if needed

---

## 📊 How It Works

### Step 1: Add Project to Config

```yaml
# config/projects.yaml
projects:
  - name: taleemabad-core
    repo: Orenda-Project/taleemabad-core
    llm:
      provider: ollama  # Start with Ollama
      model: llama3.2
    discovery:
      auto_detect: true  # Auto-detect frameworks
      guide_files:       # Look for these custom guide files
        - .github/claude.md
        - .github/review-guide.md
        - docs/CODE_STANDARDS.md
    review:
      max_comments: 8
      generate_improvements: true  # Write improvement suggestions
```

### Step 2: Bot Analyzes Codebase (First Run)

```python
# src/pr_review_bot/core/analyzer.py
class CodebaseAnalyzer:
    """Analyzes a codebase to understand structure and frameworks."""
    
    def analyze(self, repo_path: str) -> CodebaseProfile:
        """
        Analyzes the codebase and returns a profile with:
        - Detected frameworks
        - Project structure
        - Common patterns
        - Custom guide content
        """
        profile = CodebaseProfile()
        
        # 1. Detect frameworks by file patterns
        profile.frameworks = self._detect_frameworks(repo_path)
        
        # 2. Analyze project structure
        profile.structure = self._analyze_structure(repo_path)
        
        # 3. Load custom guide files (claude.md, etc.)
        profile.custom_guides = self._load_custom_guides(repo_path)
        
        # 4. Detect common patterns and conventions
        profile.patterns = self._detect_patterns(repo_path)
        
        # 5. Build comprehensive review guide
        profile.review_guide = self._build_review_guide(profile)
        
        return profile
```

### Step 3: Framework Auto-Detection

```python
class FrameworkDetector:
    """Automatically detects frameworks used in a project."""
    
    DETECTION_RULES = {
        "django": {
            "files": ["manage.py", "settings.py", "**/models.py"],
            "imports": ["from django.", "import django"],
            "confidence_threshold": 0.7
        },
        "nextjs": {
            "files": ["next.config.js", "next.config.ts", "app/**/page.tsx"],
            "imports": ["from 'next/", "import { NextPage"],
            "package_json": ["next"],
            "confidence_threshold": 0.8
        },
        "react": {
            "files": ["src/**/*.jsx", "src/**/*.tsx"],
            "imports": ["from 'react'", "import React"],
            "package_json": ["react", "react-dom"],
            "confidence_threshold": 0.7
        },
        "fastapi": {
            "files": ["main.py", "**/routers/*.py"],
            "imports": ["from fastapi", "import fastapi"],
            "requirements": ["fastapi", "uvicorn"],
            "confidence_threshold": 0.8
        },
        "flask": {
            "files": ["app.py", "**/routes/*.py"],
            "imports": ["from flask", "import Flask"],
            "requirements": ["flask"],
            "confidence_threshold": 0.8
        }
    }
    
    def detect(self, repo_path: str) -> List[FrameworkMatch]:
        """
        Scans repository and returns detected frameworks with confidence scores.
        
        Returns:
            [
                {"name": "django", "confidence": 0.95, "evidence": [...]},
                {"name": "react", "confidence": 0.85, "evidence": [...]}
            ]
        """
        matches = []
        
        for framework, rules in self.DETECTION_RULES.items():
            score = 0.0
            evidence = []
            
            # Check for specific files
            if file_matches := self._check_files(repo_path, rules.get("files", [])):
                score += 0.4
                evidence.extend(file_matches)
            
            # Check imports in Python files
            if import_matches := self._check_imports(repo_path, rules.get("imports", [])):
                score += 0.3
                evidence.extend(import_matches)
            
            # Check package.json dependencies
            if package_matches := self._check_package_json(repo_path, rules.get("package_json", [])):
                score += 0.2
                evidence.extend(package_matches)
            
            # Check requirements.txt
            if req_matches := self._check_requirements(repo_path, rules.get("requirements", [])):
                score += 0.2
                evidence.extend(req_matches)
            
            if score >= rules["confidence_threshold"]:
                matches.append({
                    "name": framework,
                    "confidence": score,
                    "evidence": evidence
                })
        
        return sorted(matches, key=lambda x: x["confidence"], reverse=True)
```

### Step 4: Custom Guide File Support

```python
class CustomGuideLoader:
    """Loads and parses project-specific guide files."""
    
    def load_guides(self, repo_path: str, guide_files: List[str]) -> str:
        """
        Looks for guide files in priority order and combines them.
        
        Supported formats:
        - .github/claude.md
        - .github/review-guide.md
        - docs/CODE_STANDARDS.md
        """
        combined_guide = ""
        
        for guide_file in guide_files:
            path = Path(repo_path) / guide_file
            if path.exists():
                content = path.read_text()
                combined_guide += f"\n\n=== {guide_file} ===\n{content}"
                logger.info(f"Loaded custom guide: {guide_file}")
        
        return combined_guide
    
    def parse_guide_sections(self, guide_content: str) -> Dict[str, str]:
        """
        Parse guide into sections for targeted reviews.
        
        Example sections:
        - Critical Rules
        - Security Standards
        - Performance Guidelines
        - Testing Requirements
        - Style Conventions
        """
        sections = {}
        current_section = None
        
        for line in guide_content.split("\n"):
            # Detect markdown headers as section boundaries
            if line.startswith("## "):
                current_section = line[3:].strip()
                sections[current_section] = ""
            elif current_section:
                sections[current_section] += line + "\n"
        
        return sections
```

---

## 📝 Example: Project-Specific Guide File

Create `.github/claude.md` in your repository:

```markdown
# Taleemabad Core - Code Review Standards

## Critical Rules

### 1. Soft-Delete Only
NEVER use `.delete()` on model instances. Always use soft-delete:
```python
# WRONG
instance.delete()

# CORRECT
instance.is_active = False
instance.save()
```

### 2. Multi-Tenancy Safety
Every database query must respect tenant boundaries:
```python
# WRONG
schools = School.objects.all()

# CORRECT
schools = School.objects.filter(tenant=current_tenant)
```

### 3. Migration Safety
- Never import models directly in migrations
- Always use `apps.get_model()`
- Provide reverse operations

## Security Standards

- All API endpoints require authentication by default
- Validate all input using serializers
- Never expose sensitive fields in API responses
- Rate limit public endpoints

## Performance Guidelines

- Use `select_related()` for foreign keys
- Use `prefetch_related()` for many-to-many
- Add indexes for frequently queried fields
- Cache expensive queries

## Testing Requirements

- Every new feature needs tests
- Use factories (factory-boy), not `.objects.create()`
- Tests must be in `tests/` directory
- Test names: `test_<action>_<condition>_<expected>`

## Style Conventions

- Follow PEP 8 (enforced by black/flake8)
- Docstrings for all public functions
- Type hints for function parameters
- Max function length: 50 lines
```

---

## 🔄 Complete Workflow Example

### Adding a New Project

```yaml
# config/projects.yaml
projects:
  # Existing project
  - name: taleemabad-core
    repo: Orenda-Project/taleemabad-core
    llm:
      provider: ollama
      model: llama3.2
    discovery:
      auto_detect: true
      guide_files:
        - .github/claude.md
  
  # NEW PROJECT - Just add these lines!
  - name: new-ecommerce-api
    repo: myorg/ecommerce-api
    llm:
      provider: ollama  # Test with Ollama first
      model: llama3.2
    discovery:
      auto_detect: true  # Will auto-detect Flask/FastAPI
      guide_files:
        - .github/review-guide.md
        - docs/API_STANDARDS.md
```

### Bot's First Run on New Project

```
$ pr-review-bot discover --project new-ecommerce-api

🔍 Analyzing new-ecommerce-api...

✓ Framework detection:
  - FastAPI (confidence: 0.92)
  - PostgreSQL (confidence: 0.85)
  - Pydantic (confidence: 0.90)

✓ Project structure:
  - API routes: /app/routers/
  - Models: /app/models/
  - Tests: /tests/

✓ Custom guides loaded:
  - .github/review-guide.md (found)
  - docs/API_STANDARDS.md (found)

✓ Pattern detection:
  - REST API structure
  - Async endpoints
  - JWT authentication
  - SQLAlchemy ORM

📝 Generated review guide saved to:
   .bot/new-ecommerce-api-review-guide.md

✅ Project ready for reviews!
```

### Generated Review Guide

The bot creates a comprehensive guide by combining:

```markdown
# new-ecommerce-api - Generated Review Guide
Generated on: 2026-03-05

## Detected Frameworks
- FastAPI 0.110.0
- PostgreSQL 15
- Pydantic v2
- SQLAlchemy 2.0

## Project Structure
```
app/
├── routers/       # API endpoints
├── models/        # SQLAlchemy models
├── schemas/       # Pydantic schemas
├── services/      # Business logic
└── dependencies/  # Dependency injection
tests/
├── unit/
└── integration/
```

## Custom Project Rules (from .github/review-guide.md)
[... content from your custom guide ...]

## Framework-Specific Best Practices

### FastAPI Best Practices
1. Use Pydantic models for request/response validation
2. Dependency injection for database sessions
3. Background tasks for long operations
4. Proper exception handlers

### SQLAlchemy Best Practices
1. Use async sessions
2. Relationship loading strategies
3. Query optimization
4. Transaction management

## Security Checks
- [ ] SQL injection prevention (parameterized queries)
- [ ] Input validation (Pydantic)
- [ ] Authentication on all private endpoints
- [ ] Rate limiting

## Common Violations to Check
[Framework-specific violations detected from codebase analysis]
```

---

## 🧪 Testing LLM Providers

### Start with Ollama (Free)

```yaml
# config/projects.yaml
projects:
  - name: taleemabad-core
    llm:
      provider: ollama
      model: llama3.2
      base_url: http://localhost:11434
```

Test the review quality:
```bash
$ pr-review-bot review --project taleemabad-core --pr 123

📊 Review Results (Ollama):
- Comments: 5
- Quality Score: 7/10
- Review Time: 45s
- Cost: $0.00
```

### Switch to Claude if Needed

```yaml
# config/projects.yaml
projects:
  - name: taleemabad-core
    llm:
      provider: anthropic  # Changed from ollama
      model: claude-sonnet-4
      api_key: ${ANTHROPIC_API_KEY}
```

Test again:
```bash
$ pr-review-bot review --project taleemabad-core --pr 123

📊 Review Results (Claude):
- Comments: 7
- Quality Score: 9/10
- Review Time: 12s
- Cost: $0.05
```

Compare and decide which provider to use!

---

## 📈 Improvement Generation

After each review, the bot can generate structured improvements:

```python
class ImprovementGenerator:
    """Generates actionable improvement suggestions."""
    
    def generate_improvements(
        self, 
        pr: PullRequest, 
        review: Review,
        codebase_profile: CodebaseProfile
    ) -> ImprovementReport:
        """
        Analyzes review results and generates improvement suggestions.
        
        Output saved to: .bot/improvements/{project}/{date}.md
        """
        improvements = []
        
        # Analyze patterns in violations
        violation_patterns = self._analyze_violations(review.comments)
        
        # Suggest systemic improvements
        if violation_patterns.get("missing_tests") > 3:
            improvements.append({
                "category": "Testing",
                "priority": "high",
                "suggestion": "Consider implementing test coverage requirements in CI",
                "impact": "Prevents untested code from being merged"
            })
        
        if violation_patterns.get("hard_delete") > 0:
            improvements.append({
                "category": "Data Safety",
                "priority": "critical",
                "suggestion": "Add pre-commit hook to prevent .delete() calls",
                "impact": "Prevents accidental data loss"
            })
        
        # Generate report
        report = ImprovementReport(
            project=pr.project,
            date=datetime.now(),
            pr_number=pr.number,
            improvements=improvements
        )
        
        # Save to file
        self._save_report(report)
        
        return report
```

### Example Improvement Report

```markdown
# Improvement Report - taleemabad-core
Date: 2026-03-05
PR: #456

## Critical Findings

### 1. Data Safety Violations (Priority: CRITICAL)
**Pattern:** 2 instances of `.delete()` found in this PR
**Root Cause:** Developers may not be aware of soft-delete requirement
**Recommendation:** 
- Add pre-commit hook to block `.delete()` calls
- Add linting rule to flag hard deletes
- Update developer onboarding docs

**Implementation:**
```python
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: no-hard-delete
        name: Prevent hard deletes
        entry: python scripts/check_no_delete.py
        language: python
        files: \.py$
```

### 2. Missing Test Coverage (Priority: HIGH)
**Pattern:** 3 new functions with no tests
**Root Cause:** Tests not required in PR checklist
**Recommendation:**
- Add test coverage check to CI
- Require 80% coverage for new code
- Block merge if coverage drops

## Medium Priority Improvements

### 3. Inconsistent Import Style
- Suggest: Add isort to pre-commit
- Impact: Better code consistency

### 4. Long Functions Detected
- 2 functions > 50 lines
- Suggest: Refactoring guidelines

## Trends Over Time
- Soft-delete violations: Decreasing ✓
- Test coverage: Improving ✓
- Security issues: Stable

## Next Review Focus Areas
- [ ] API serializer security
- [ ] Database query optimization
- [ ] Error handling patterns
```

---

## 🔧 Implementation Architecture

```python
# src/pr_review_bot/core/smart_reviewer.py
class SmartReviewer:
    """Intelligent reviewer that learns about codebases."""
    
    def __init__(self, project_config: ProjectSettings):
        self.config = project_config
        self.analyzer = CodebaseAnalyzer()
        self.guide_loader = CustomGuideLoader()
        self.llm = self._create_llm_provider()
    
    def initialize_project(self) -> CodebaseProfile:
        """
        First-time setup for a project:
        1. Clone repo (or use existing clone)
        2. Analyze codebase
        3. Load custom guides
        4. Generate comprehensive review guide
        5. Cache the profile
        """
        logger.info(f"Initializing project: {self.config.name}")
        
        # Analyze codebase
        profile = self.analyzer.analyze(self.config.repo_path)
        
        # Load custom guides
        custom_guides = self.guide_loader.load_guides(
            self.config.repo_path,
            self.config.discovery.guide_files
        )
        profile.custom_guides = custom_guides
        
        # Build comprehensive review guide
        profile.review_guide = self._build_comprehensive_guide(profile)
        
        # Cache the profile
        self._save_profile(profile)
        
        logger.info(f"✓ Project initialized. Detected: {profile.frameworks}")
        return profile
    
    def review_pr(self, pr: PullRequest) -> Review:
        """
        Review a PR using the project's profile and custom guides.
        """
        # Load cached profile or initialize
        profile = self._load_profile() or self.initialize_project()
        
        # Build context-aware prompt
        prompt = self._build_review_prompt(pr, profile)
        
        # Call LLM (Ollama or Claude)
        result = self.llm.review(prompt, pr.diff)
        
        # Generate improvements
        if self.config.review.generate_improvements:
            improvements = self.improvement_generator.generate(pr, result, profile)
        
        return result
    
    def _build_comprehensive_guide(self, profile: CodebaseProfile) -> str:
        """
        Combines:
        - Framework-specific best practices
        - Custom project guides (claude.md)
        - Detected patterns and conventions
        - Previous review insights
        """
        sections = []
        
        # 1. Project context
        sections.append(f"# Review Guide: {self.config.name}\n")
        sections.append(f"Frameworks: {', '.join(profile.frameworks)}\n")
        
        # 2. Custom project rules
        if profile.custom_guides:
            sections.append("\n## Custom Project Rules\n")
            sections.append(profile.custom_guides)
        
        # 3. Framework best practices
        for framework in profile.frameworks:
            sections.append(f"\n## {framework.title()} Best Practices\n")
            sections.append(self._get_framework_guide(framework))
        
        # 4. Detected patterns
        sections.append("\n## Project Patterns & Conventions\n")
        sections.append(self._format_patterns(profile.patterns))
        
        return "\n".join(sections)
```

---

## 📦 Minimal Configuration

With smart discovery, your config is super simple:

```yaml
# config/projects.yaml
projects:
  - name: taleemabad-core
    repo: Orenda-Project/taleemabad-core
    llm:
      provider: ollama
      model: llama3.2
    discovery:
      auto_detect: true
      guide_files:
        - .github/claude.md

  - name: new-project
    repo: myorg/new-project
    llm:
      provider: ollama
      model: llama3.2
    discovery:
      auto_detect: true
      guide_files:
        - .github/review-guide.md

# That's it! No framework config needed.
```

---

## 🚀 CLI Commands

```bash
# Discover/analyze a new project
pr-review-bot discover --project taleemabad-core

# Review PRs (uses cached analysis)
pr-review-bot review --project taleemabad-core

# Test Ollama vs Claude on same PR
pr-review-bot compare --project taleemabad-core --pr 123 --providers ollama,anthropic

# Generate improvement report
pr-review-bot improve --project taleemabad-core --since 2026-03-01

# Update project analysis (re-scan codebase)
pr-review-bot refresh --project taleemabad-core
```

---

## ✅ Benefits of This Approach

1. **Zero Framework Config** - Just add repo URL
2. **Project-Specific Rules** - Use `claude.md` for custom guidelines
3. **Flexible LLM Choice** - Test Ollama, switch to Claude easily
4. **Learning System** - Improves over time from past reviews
5. **Low Maintenance** - Auto-detects changes in codebase
6. **Actionable Insights** - Generates improvement reports

---

**This is exactly what you need: Add a project → Bot learns about it → Start reviewing! 🎯**
