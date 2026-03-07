"""Configuration loader."""
import yaml
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from .settings import Settings, ProjectSettings

# Load environment variables from .env file
load_dotenv()


def load_config(config_path: str = "config/projects.yaml") -> Settings:
    """Load configuration from YAML file.
    
    Args:
        config_path: Path to projects.yaml file
        
    Returns:
        Settings object with all project configurations
    """
    path = Path(config_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(path) as f:
        data = yaml.safe_load(f)
    
    if not data or "projects" not in data:
        raise ValueError(f"Invalid config file: {config_path}. Must contain 'projects' key.")
    
    projects = [ProjectSettings(**p) for p in data["projects"]]
    return Settings(projects=projects)


def get_project_config(project_name: str, config_path: str = "config/projects.yaml") -> Optional[ProjectSettings]:
    """Get configuration for a specific project.
    
    Args:
        project_name: Project name to find
        config_path: Path to projects.yaml file
        
    Returns:
        ProjectSettings if found, None otherwise
    """
    settings = load_config(config_path)
    
    for project in settings.projects:
        if project.name == project_name:
            return project
    
    return None
