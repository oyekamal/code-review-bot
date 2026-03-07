"""Configuration models using Pydantic."""
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from typing import Optional, List
import os


class LLMConfig(BaseModel):
    """LLM provider configuration."""
    provider: str = "ollama"  # ollama | anthropic
    model: str = "llama3.2"
    base_url: Optional[str] = "http://localhost:11434"
    api_key_env: Optional[str] = None


class DiscoveryConfig(BaseModel):
    """Project discovery configuration."""
    auto_detect: bool = True
    frameworks: List[str] = Field(default_factory=list)  # Override auto-detection
    guide_files: List[str] = Field(default_factory=lambda: [".github/claude.md"])


class ReviewConfig(BaseModel):
    """Review behavior configuration."""
    max_comments: int = 8
    auto_approve_on_resolution: bool = True
    generate_improvements: bool = True
    target_branch: Optional[str] = "develop"  # Only review PRs targeting this branch


class ProjectSettings(BaseModel):
    """Single project configuration."""
    name: str
    repo: str  # Format: owner/repo-name
    github_token_env: str = "GITHUB_TOKEN"
    llm: LLMConfig = Field(default_factory=LLMConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)

    def get_github_token(self) -> str:
        """Get GitHub token from environment."""
        token = os.getenv(self.github_token_env)
        if not token:
            raise ValueError(f"Environment variable {self.github_token_env} not set")
        return token

    def get_llm_api_key(self) -> Optional[str]:
        """Get LLM API key from environment if configured."""
        if self.llm.api_key_env:
            return os.getenv(self.llm.api_key_env)
        return None


class Settings(BaseSettings):
    """Global settings."""
    projects: List[ProjectSettings] = Field(default_factory=list)
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"
