# Implementation Roadmap - Smart Discovery System

Based on your requirements:
- ✅ Currently 1 project (taleemabad-core)
- ✅ Want easy project addition (just add to config)
- ✅ Test with Ollama first, switch to Claude if needed
- ✅ Support custom guides (claude.md files)

---

## 🎯 Implementation Phases

### Phase 1: Foundation (3-5 days)

**Goal:** Keep current bot working, add smart discovery alongside

#### Day 1-2: Config System
```bash
# Create new structure alongside existing scripts
mkdir -p config src/pr_review_bot/{core,integrations,models}
```

**Files to create:**

1. **config/projects.yaml** - Your multi-project config
```yaml
projects:
  - name: taleemabad-core
    repo: Orenda-Project/taleemabad-core
    llm:
      provider: ollama
      model: llama3.2
      base_url: http://localhost:11434
    discovery:
      auto_detect: true
      guide_files:
        - .github/claude.md
        - pr-review-bot/guides/CODE_REVIEW_GUIDE.md
    review:
      max_comments: 8
      generate_improvements: true
```

2. **src/pr_review_bot/config/settings.py** - Pydantic models
```python
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from typing import Optional, List

class LLMConfig(BaseModel):
    provider: str = "ollama"  # ollama | anthropic
    model: str = "llama3.2"
    base_url: Optional[str] = "http://localhost:11434"
    api_key: Optional[str] = None

class DiscoveryConfig(BaseModel):
    auto_detect: bool = True
    frameworks: List[str] = []  # Override auto-detection
    guide_files: List[str] = [".github/claude.md"]

class ReviewConfig(BaseModel):
    max_comments: int = 8
    auto_approve_on_resolution: bool = True
    generate_improvements: bool = True

class ProjectSettings(BaseModel):
    name: str
    repo: str
    llm: LLMConfig = LLMConfig()
    discovery: DiscoveryConfig = DiscoveryConfig()
    review: ReviewConfig = ReviewConfig()

class Settings(BaseSettings):
    github_token: str
    bot_username: str
    projects: List[ProjectSettings] = []
    
    class Config:
        env_file = ".env"
```

3. **src/pr_review_bot/config/loader.py** - Load YAML
```python
import yaml
from pathlib import Path
from .settings import Settings, ProjectSettings

def load_config(config_path: str = "config/projects.yaml") -> Settings:
    with open(config_path) as f:
        data = yaml.safe_load(f)
    
    projects = [ProjectSettings(**p) for p in data["projects"]]
    return Settings(projects=projects)
```

#### Day 3: Framework Auto-Detection
```python
# src/pr_review_bot/core/detector.py
from pathlib import Path
from typing import List, Dict
import os

class FrameworkDetector:
    """Auto-detect frameworks from codebase structure."""
    
    DETECTION_RULES = {
        "django": {
            "files": ["manage.py", "settings.py"],
            "patterns": ["**/models.py", "**/views.py"],
        },
        "nextjs": {
            "files": ["next.config.js", "next.config.ts"],
            "patterns": ["app/**/page.tsx"],
        },
        "react": {
            "patterns": ["src/**/*.jsx", "src/**/*.tsx"],
        },
    }
    
    def detect(self, repo_path: str) -> List[str]:
        """Scan repo and return detected frameworks."""
        detected = []
        
        for framework, rules in self.DETECTION_RULES.items():
            if self._check_framework(repo_path, rules):
                detected.append(framework)
        
        return detected
    
    def _check_framework(self, repo_path: str, rules: Dict) -> bool:
        # Check for specific files
        for filename in rules.get("files", []):
            if self._file_exists(repo_path, filename):
                return True
        
        # Check for file patterns
        for pattern in rules.get("patterns", []):
            if self._pattern_exists(repo_path, pattern):
                return True
        
        return False
    
    def _file_exists(self, repo_path: str, filename: str) -> bool:
        return Path(repo_path).rglob(filename).__next__() if True else False
    
    def _pattern_exists(self, repo_path: str, pattern: str) -> bool:
        matches = list(Path(repo_path).rglob(pattern))
        return len(matches) > 0
```

#### Day 4-5: Guide Loader & LLM Integration
```python
# src/pr_review_bot/core/guide_loader.py
from pathlib import Path
from typing import List

class GuideLoader:
    """Load custom guide files from projects."""
    
    def load_guides(self, repo_path: str, guide_files: List[str]) -> str:
        """Load and combine guide files."""
        combined = ""
        
        for guide_file in guide_files:
            path = Path(repo_path) / guide_file
            if path.exists():
                content = path.read_text()
                combined += f"\n\n=== {guide_file} ===\n{content}"
                print(f"✓ Loaded: {guide_file}")
            else:
                print(f"⚠ Not found: {guide_file}")
        
        return combined
```

```python
# src/pr_review_bot/integrations/llm/base.py
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    def review(self, guide: str, diff: str) -> dict:
        pass

# src/pr_review_bot/integrations/llm/ollama.py
import requests

class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model
    
    def review(self, guide: str, diff: str) -> dict:
        # Your existing call_ollama logic
        prompt = f"{guide}\n\nDIFF:\n{diff}\n\nReturn JSON review."
        
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=120
        )
        
        return self._parse_response(response.json()["response"])
    
    def _parse_response(self, text: str) -> dict:
        # Your existing _parse_ollama_json logic
        import json
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])

# src/pr_review_bot/integrations/llm/anthropic.py
import anthropic

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
    
    def review(self, guide: str, diff: str) -> dict:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": f"{guide}\n\nDIFF:\n{diff}\n\nReturn JSON review."
            }]
        )
        
        return self._parse_response(response.content[0].text)
    
    def _parse_response(self, text: str) -> dict:
        import json
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
```

---

### Phase 2: Smart Reviewer (3-5 days)

#### Day 6-7: Core Reviewer Logic
```python
# src/pr_review_bot/core/smart_reviewer.py
from ..config.settings import ProjectSettings
from ..integrations.github.client import GitHubClient
from .detector import FrameworkDetector
from .guide_loader import GuideLoader

class SmartReviewer:
    """Intelligent reviewer with auto-discovery."""
    
    def __init__(self, config: ProjectSettings, github_token: str):
        self.config = config
        self.github = GitHubClient(github_token, config.repo)
        self.detector = FrameworkDetector()
        self.guide_loader = GuideLoader()
        self.llm = self._create_llm()
    
    def _create_llm(self):
        if self.config.llm.provider == "ollama":
            from ..integrations.llm.ollama import OllamaProvider
            return OllamaProvider(
                self.config.llm.base_url,
                self.config.llm.model
            )
        elif self.config.llm.provider == "anthropic":
            from ..integrations.llm.anthropic import AnthropicProvider
            return AnthropicProvider(
                self.config.llm.api_key,
                self.config.llm.model
            )
    
    def discover_project(self, repo_path: str):
        """First-time project analysis."""
        print(f"🔍 Analyzing {self.config.name}...")
        
        # Detect frameworks
        frameworks = self.detector.detect(repo_path)
        print(f"✓ Detected: {', '.join(frameworks)}")
        
        # Load custom guides
        guides = self.guide_loader.load_guides(
            repo_path,
            self.config.discovery.guide_files
        )
        
        # Cache for future use
        self._save_profile(frameworks, guides)
        
        return frameworks, guides
    
    def review_pr(self, pr_number: int):
        """Review a pull request."""
        # Get PR diff
        pr_data = self.github.get_pr(pr_number)
        diff = self.github.get_pr_diff(pr_number)
        
        # Load cached profile or discover
        frameworks, guides = self._load_profile()
        
        # Review with LLM
        result = self.llm.review(guides, diff)
        
        # Post to GitHub
        self.github.post_review(pr_number, result)
        
        return result
    
    def _save_profile(self, frameworks, guides):
        # Save to .bot/profiles/{project}.json
        import json
        Path(".bot/profiles").mkdir(parents=True, exist_ok=True)
        
        profile = {
            "frameworks": frameworks,
            "guide_hash": hash(guides),
            "timestamp": datetime.now().isoformat()
        }
        
        with open(f".bot/profiles/{self.config.name}.json", "w") as f:
            json.dump(profile, f, indent=2)
    
    def _load_profile(self):
        # Load from cache or re-discover
        profile_path = Path(f".bot/profiles/{self.config.name}.json")
        if profile_path.exists():
            # Load cached
            pass
        else:
            # Discover
            return self.discover_project(repo_path)
```

#### Day 8-9: CLI Interface
```python
# src/pr_review_bot/cli/commands.py
import click
from ..config.loader import load_config
from ..core.smart_reviewer import SmartReviewer

@click.group()
def cli():
    """PR Review Bot - Smart Discovery Mode"""
    pass

@cli.command()
@click.option("--project", required=True)
@click.option("--repo-path", default=".")
def discover(project, repo_path):
    """Analyze a project and detect frameworks."""
    config = load_config()
    project_config = next(p for p in config.projects if p.name == project)
    
    reviewer = SmartReviewer(project_config, config.github_token)
    frameworks, guides = reviewer.discover_project(repo_path)
    
    click.echo(f"✅ Project ready! Detected: {', '.join(frameworks)}")

@cli.command()
@click.option("--project", required=True)
@click.option("--pr", type=int)
def review(project, pr):
    """Review PRs for a project."""
    config = load_config()
    project_config = next(p for p in config.projects if p.name == project)
    
    reviewer = SmartReviewer(project_config, config.github_token)
    
    if pr:
        # Review specific PR
        reviewer.review_pr(pr)
    else:
        # Review all open PRs
        prs = reviewer.github.list_open_prs()
        for pr_data in prs:
            reviewer.review_pr(pr_data["number"])

@cli.command()
@click.option("--project", required=True)
@click.option("--pr", type=int, required=True)
@click.option("--providers", default="ollama,anthropic")
def compare(project, pr, providers):
    """Compare LLM providers on same PR."""
    # Run review with both Ollama and Claude
    # Show side-by-side comparison
    pass

if __name__ == "__main__":
    cli()
```

#### Day 10: Testing
```bash
# Test discovery
pr-review-bot discover --project taleemabad-core --repo-path /path/to/repo

# Test review with Ollama
pr-review-bot review --project taleemabad-core --pr 123

# Compare Ollama vs Claude
pr-review-bot compare --project taleemabad-core --pr 123 --providers ollama,anthropic
```

---

### Phase 3: Parallel Deployment (1 week)

Run old script AND new system side-by-side:

```bash
# Old cron job (keep running)
0 */3 * * * python3 /path/scripts/pr_review_bot.py >> /var/log/pr_review_bot.log 2>&1

# New CLI (manual testing)
# Test on specific PRs to verify
```

Compare outputs, fix any issues, then switch fully to new system.

---

### Phase 4: Production Cutover (When ready)

```bash
# Update cron to use new CLI
0 */3 * * * pr-review-bot review --project taleemabad-core >> /var/log/pr_review_bot.log 2>&1

# Archive old scripts
mv scripts/pr_review_bot.py scripts/ARCHIVED_pr_review_bot.py.bak
```

---

## 📊 Expected Timeline

| Phase | Duration | Status |
|-------|----------|--------|
| Phase 1: Foundation | 5 days | ⏳ Next |
| Phase 2: Smart Reviewer | 5 days | ⏳ |
| Phase 3: Parallel Testing | 7 days | ⏳ |
| Phase 4: Cutover | 1 day | ⏳ |
| **Total** | **~3 weeks** | |

---

## ✅ Success Criteria

After implementation, you should be able to:

- [ ] Add new project in 5 minutes (edit YAML only)
- [ ] Bot auto-detects frameworks (Django, Next.js, React, etc.)
- [ ] Custom guides loaded from `.github/claude.md`
- [ ] Compare Ollama vs Claude quality
- [ ] Switch LLM providers via config (no code changes)
- [ ] Review multiple projects from one bot
- [ ] Generate improvement reports

---

## 🎯 Quick Start (Today)

Want to start right now? Do the minimal version:

1. **Create .github/claude.md in taleemabad-core**
   - Copy your existing guides into it
   
2. **Create config/projects.yaml**
   - Simple YAML config (see Phase 1)

3. **Test framework detection**
   - Write 20-line script to scan for Django/React files
   - Print detected frameworks

4. **Compare Ollama vs Claude manually**
   - Run same PR through both
   - See which gives better results

This gives you 70% of the value in 1 day!

---

## 🆘 Need Help?

I can help implement any specific component:
- Framework detector
- Guide loader
- LLM abstraction
- CLI commands
- Testing strategy

Just let me know which part you want to tackle first!

---

**You're now equipped with everything you need to build this smart discovery system! 🚀**
