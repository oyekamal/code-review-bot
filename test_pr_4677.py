#!/usr/bin/env python3
"""Quick test script for PR #4677."""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pr_review_bot.config import get_project_config
from pr_review_bot.core.smart_reviewer import SmartReviewer
from pr_review_bot.core.logger import setup_logging
from rich.console import Console
from rich.panel import Panel

console = Console()


def main():
    """Test PR #4677 review."""
    # Setup logging
    setup_logging("INFO")
    
    console.print(Panel.fit(
        "[bold cyan]PR Review Bot - Test Run[/bold cyan]\n\n"
        "Testing PR #4677 in taleemabad-core",
        title="🧪 Test Runner"
    ))
    
    # Load configuration
    console.print("\n[yellow]1. Loading configuration...[/yellow]")
    try:
        project_config = get_project_config("taleemabad-core", "config/projects.yaml")
        if not project_config:
            console.print("[red]❌ Project 'taleemabad-core' not found in config/projects.yaml[/red]")
            console.print("[yellow]💡 Make sure config/projects.yaml exists and has taleemabad-core configured[/yellow]")
            return 1
        
        console.print(f"[green]✓ Loaded config for {project_config.name}[/green]")
        console.print(f"  Repo: {project_config.repo}")
        console.print(f"  LLM: {project_config.llm.provider} ({project_config.llm.model})")
    except Exception as e:
        console.print(f"[red]❌ Config error: {e}[/red]")
        return 1
    
    # Check GitHub token
    console.print("\n[yellow]2. Checking GitHub authentication...[/yellow]")
    try:
        token = project_config.get_github_token()
        console.print(f"[green]✓ GitHub token found ({token[:10]}...)[/green]")
    except Exception as e:
        console.print(f"[red]❌ GitHub token error: {e}[/red]")
        console.print("[yellow]💡 Run: gh auth login[/yellow]")
        console.print("[yellow]💡 Or set GITHUB_TOKEN environment variable[/yellow]")
        return 1
    
    # Check LLM availability
    console.print("\n[yellow]3. Checking LLM availability...[/yellow]")
    try:
        reviewer = SmartReviewer(project_config)
        if reviewer.llm.health_check():
            console.print(f"[green]✓ {project_config.llm.provider} is available[/green]")
        else:
            console.print(f"[red]⚠ {project_config.llm.provider} health check failed[/red]")
            if project_config.llm.provider == "ollama":
                console.print("[yellow]💡 Make sure Ollama is running: ollama serve[/yellow]")
                console.print("[yellow]💡 And llama3.2 is installed: ollama pull llama3.2[/yellow]")
    except Exception as e:
        console.print(f"[red]❌ LLM error: {e}[/red]")
        return 1
    
    # Fetch PR #4677
    console.print("\n[yellow]4. Fetching PR #4677...[/yellow]")
    try:
        pr = reviewer.github.get_pr(4677)
        console.print(f"[green]✓ Found PR: {pr.title}[/green]")
        console.print(f"  Author: {pr.user.login}")
        console.print(f"  State: {pr.state}")
        console.print(f"  Created: {pr.created_at}")
    except Exception as e:
        console.print(f"[red]❌ PR fetch error: {e}[/red]")
        return 1
    
    # Review PR (dry run)
    console.print("\n[yellow]5. Generating review (this may take 1-2 minutes)...[/yellow]")
    try:
        review_result = reviewer.review_pr(4677)
        
        console.print(Panel.fit(
            f"[bold]{review_result['event']}[/bold]\n\n{review_result['summary']}",
            title="📝 Review Result"
        ))
        
        comments = review_result.get("comments", [])
        if comments:
            console.print(f"\n[bold]💬 Comments ({len(comments)}):[/bold]")
            for i, comment in enumerate(comments[:5], 1):
                console.print(f"\n{i}. [cyan]{comment['path']}:{comment['line']}[/cyan]")
                console.print(f"   {comment['body']}")
            
            if len(comments) > 5:
                console.print(f"\n[yellow]... and {len(comments) - 5} more comments[/yellow]")
        
        # Ask to post
        console.print(f"\n[bold yellow]📤 Post this review to GitHub?[/bold yellow]")
        response = input("Type 'yes' to post, anything else to skip: ").strip().lower()
        
        if response == "yes":
            reviewer.post_review(4677, review_result)
            console.print("[green]✅ Review posted to GitHub![/green]")
        else:
            console.print("[yellow]⏭ Skipped posting (dry run)[/yellow]")
        
        console.print("\n[green]✅ Test completed successfully![/green]")
        return 0
        
    except Exception as e:
        console.print(f"[red]❌ Review error: {e}[/red]")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
