# PR Review Bot 2.0 - Smart Discovery System 🤖

A modular, multi-project PR review bot with automatic framework detection and custom guide support.

## ✨ Features

- 🔍 **Smart Discovery**: Auto-detects Django, Next.js, React, FastAPI frameworks
- 📖 **Custom Guides**: Load project-specific review rules from your repo
- 🤖 **Dual LLM Support**: Use Ollama (free/local) or Claude (cloud)
- 🎯 **Multi-Project**: Manage multiple repositories from one config
- 💬 **Intelligent Reviews**: Contextual code review with actionable feedback
- 🚀 **CLI Interface**: Simple commands for all operations

## 🚀 Quick Start (5 minutes)

### 1. Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install the package in development mode
pip install -e .

# Authenticate with GitHub
gh auth login
```

### 2. Set Up Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your tokens
nano .env
```

Required environment variables:
- `GITHUB_TOKEN`: Your GitHub personal access token (or use `gh auth login`)
- `ANTHROPIC_API_KEY`: (optional) For Claude provider

### 3. Configure Your Project

The `config/projects.yaml` is already configured for taleemabad-core. Edit if needed:

```yaml
projects:
  - name: taleemabad-core
    repo: Orenda-Project/taleemabad-core
    github_token_env: GITHUB_TOKEN
    llm:
      provider: ollama  # or: anthropic
      model: llama3.2
      base_url: http://localhost:11434
```

### 4. Start Ollama (if using local LLM)

```bash
# Start Ollama server
ollama serve

# In another terminal, pull the model
ollama pull llama3.2
```

### 5. Test on PR #4677

```bash
# Quick test script
python test_pr_4677.py

# Or use CLI
pr-review-bot review --project taleemabad-core --pr 4677 --dry-run
```

## 📋 CLI Commands

### List Projects
```bash
pr-review-bot list-projects
```

### List Open PRs
```bash
pr-review-bot list-prs --project taleemabad-core
```

### Discover Project
```bash
# Detect frameworks and load guides
pr-review-bot discover --project taleemabad-core
```

### Review Single PR
```bash
# Dry run (don't post)
pr-review-bot review --project taleemabad-core --pr 4677 --dry-run

# Post to GitHub
pr-review-bot review --project taleemabad-core --pr 4677
```

### Review All Open PRs
```bash
pr-review-bot review --project taleemabad-core
```

### Test LLM
```bash
# Test review generation without posting
pr-review-bot test-llm --project taleemabad-core --pr 4677
```

## 📁 Project Structure

```
code-review-bot/
├── config/
│   └── projects.yaml          # Multi-project configuration
├── src/pr_review_bot/
│   ├── config/                # Configuration models
│   │   ├── settings.py        # Pydantic models
│   │   └── loader.py          # YAML loader
│   ├── core/                  # Core logic
│   │   ├── detector.py        # Framework auto-detection
│   │   ├── guide_loader.py    # Custom guide loader
│   │   ├── logger.py          # Logging setup
│   │   └── smart_reviewer.py  # Main orchestrator
│   ├── integrations/          # External integrations
│   │   ├── github/            # GitHub API client
│   │   │   └── client.py
│   │   └── llm/               # LLM providers
│   │       ├── base.py        # Abstract interface
│   │       ├── ollama.py      # Ollama provider
│   │       └── anthropic.py   # Claude provider
│   └── cli/                   # Command-line interface
│       └── commands.py
├── guides/                    # Review guides
│   ├── CODE_REVIEW_GUIDE.md
│   └── TEST_REVIEW_GUIDE.md
├── logs/                      # Log files
├── .bot/profiles/             # Cached project profiles
└── test_pr_4677.py           # Quick test script
```

## 🔧 Configuration Options

### LLM Providers

**Ollama (Local, Free)**
```yaml
llm:
  provider: ollama
  model: llama3.2
  base_url: http://localhost:11434
```

**Anthropic Claude (Cloud)**
```yaml
llm:
  provider: anthropic
  model: claude-3-5-sonnet-20241022
  api_key_env: ANTHROPIC_API_KEY
```

### Discovery Options

```yaml
discovery:
  auto_detect: true              # Auto-detect frameworks
  guide_files:                   # Custom guide files
    - guides/CODE_REVIEW_GUIDE.md
    - guides/TEST_REVIEW_GUIDE.md
```

### Review Options

```yaml
review:
  max_comments: 8                      # Limit comments per review
  auto_approve_on_resolution: false    # Auto-approve when issues fixed
  generate_improvements: true          # Generate improvement suggestions
```

## 🧪 Testing

### Test on PR #4677

```bash
# Method 1: Quick test script
python test_pr_4677.py

# Method 2: CLI dry run
pr-review-bot review --project taleemabad-core --pr 4677 --dry-run

# Method 3: CLI with confirmation
pr-review-bot review --project taleemabad-core --pr 4677
```

### Test Framework Detection

```bash
# Clone the repo and test detection
git clone https://github.com/Orenda-Project/taleemabad-core.git /tmp/test-repo
pr-review-bot discover --project taleemabad-core --repo-path /tmp/test-repo
```

## 📖 Adding New Projects

1. Edit `config/projects.yaml`:
```yaml
projects:
  - name: my-new-project
    repo: org/repo-name
    github_token_env: GITHUB_TOKEN
    llm:
      provider: ollama
      model: llama3.2
```

2. Discover the project:
```bash
pr-review-bot discover --project my-new-project
```

3. Review PRs:
```bash
pr-review-bot review --project my-new-project --pr 123
```

## 🔍 Framework Detection

The bot automatically detects:

- **Django**: `manage.py`, `settings.py`, `models.py`, `views.py`
- **Next.js**: `next.config.js`, `app/**/page.tsx`, `pages/**/*.tsx`
- **React**: `package.json` with react dependency, `src/**/*.jsx`
- **FastAPI**: `main.py` with fastapi in requirements
- **Flask**: `app.py` with flask in requirements

## 📝 Custom Guides

Create `.github/claude.md` in your repository:

```markdown
# Project-Specific Review Rules

## Critical Rules
1. Always use soft-delete (never .delete())
2. Multi-tenancy safety required
3. No breaking API changes

## What to Flag
- Hard deletes
- Missing tenant context
- Security issues
```

The bot will automatically load and use these rules!

## 🐛 Troubleshooting

### "Project not found in config"
- Check `config/projects.yaml` exists
- Verify project name matches exactly

### "GitHub token not found"
```bash
# Option 1: Use gh CLI
gh auth login

# Option 2: Set environment variable
export GITHUB_TOKEN=ghp_your_token_here
```

### "Ollama health check failed"
```bash
# Start Ollama
ollama serve

# Check if model is installed
ollama list

# Pull model if needed
ollama pull llama3.2
```

### "Review generation failed"
- Check LLM is running (Ollama or Claude API)
- Verify model name is correct
- Check internet connection (for Claude)
- Look at logs in `logs/pr_review_bot.log`

## 📊 Logs

All operations are logged to:
- **Console**: INFO level (colored output)
- **File**: `logs/pr_review_bot.log` (DEBUG level, JSON format)

View logs:
```bash
tail -f logs/pr_review_bot.log | jq .
```

## 🎯 Next Steps

1. **Test on PR #4677**: Run `python test_pr_4677.py`
2. **Review all open PRs**: `pr-review-bot review --project taleemabad-core`
3. **Compare LLMs**: Test both Ollama and Claude to see which works better
4. **Add more projects**: Edit `config/projects.yaml`
5. **Automate**: Set up cron job or GitHub Actions

## 📚 Documentation

- [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) - Full implementation plan
- [ARCHITECTURE_PROPOSAL.md](ARCHITECTURE_PROPOSAL.md) - Architecture deep dive
- [SMART_DISCOVERY_GUIDE.md](SMART_DISCOVERY_GUIDE.md) - Discovery system details
- [QUICK_START.md](QUICK_START.md) - Quick start guide

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

MIT License - See LICENSE file for details

---

**Ready to test? Run: `python test_pr_4677.py`** 🚀
