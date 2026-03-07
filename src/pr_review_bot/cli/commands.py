"""CLI commands for PR review bot."""
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint
import sys
from pathlib import Path

from ..config import load_config, get_project_config
from ..core.smart_reviewer import SmartReviewer
from ..core.logger import setup_logging

console = Console()


@click.group()
@click.option("--log-level", default="INFO", help="Logging level")
@click.option("--config", default="config/projects.yaml", help="Path to config file")
@click.pass_context
def cli(ctx, log_level, config):
    """PR Review Bot - Smart Discovery Mode 🤖"""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config
    ctx.obj["log_level"] = log_level
    
    # Setup logging
    setup_logging(log_level)


@cli.command()
@click.pass_context
def list_projects(ctx):
    """List all configured projects."""
    try:
        config = load_config(ctx.obj["config_path"])
        
        table = Table(title="📋 Configured Projects")
        table.add_column("Name", style="cyan")
        table.add_column("Repository", style="green")
        table.add_column("LLM Provider", style="yellow")
        table.add_column("Model", style="magenta")
        
        for project in config.projects:
            table.add_row(
                project.name,
                project.repo,
                project.llm.provider,
                project.llm.model
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--project", required=True, help="Project name")
@click.option("--repo-path", help="Path to cloned repo (optional, will clone if not provided)")
@click.pass_context
def discover(ctx, project, repo_path):
    """Discover frameworks and load guides for a project."""
    try:
        project_config = get_project_config(project, ctx.obj["config_path"])
        if not project_config:
            console.print(f"[red]❌ Project '{project}' not found in config[/red]")
            sys.exit(1)
        
        reviewer = SmartReviewer(project_config)
        
        # Clone if needed
        if not repo_path:
            console.print(f"[yellow]📥 Cloning repository...[/yellow]")
            repo_path = reviewer._clone_repo()
        
        # Discover
        frameworks, guides = reviewer.discover_project(repo_path)
        
        # Show results
        console.print(Panel.fit(
            f"[green]✅ Project Discovered![/green]\n\n"
            f"Frameworks: {', '.join(frameworks) if frameworks else 'None detected'}\n"
            f"Guides loaded: {len(guides)} characters",
            title=f"📦 {project}"
        ))
        
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--project", required=True, help="Project name")
@click.option("--pr", type=int, help="PR number (leave empty to review all open PRs)")
@click.option("--repo-path", help="Path to cloned repo (optional)")
@click.option("--dry-run", is_flag=True, help="Generate review but don't post to GitHub")
@click.pass_context
def review(ctx, project, pr, repo_path, dry_run):
    """Review pull request(s) in a project."""
    try:
        project_config = get_project_config(project, ctx.obj["config_path"])
        if not project_config:
            console.print(f"[red]❌ Project '{project}' not found in config[/red]")
            sys.exit(1)
        
        reviewer = SmartReviewer(project_config)
        
        if pr:
            # Review single PR
            console.print(f"[cyan]🔍 Reviewing PR #{pr}...[/cyan]")
            review_result = reviewer.review_pr(pr, repo_path)
            
            # Show result
            _display_review(pr, review_result)
            
            # Post to GitHub
            if not dry_run:
                reviewer.post_review(pr, review_result)
                console.print(f"[green]✅ Review posted to GitHub[/green]")
            else:
                console.print(f"[yellow]🔒 Dry run - review not posted[/yellow]")
        else:
            # Review all open PRs
            console.print(f"[cyan]🔍 Reviewing all open PRs...[/cyan]")
            results = reviewer.review_all_open_prs(repo_path)
            
            # Show summary
            successful = sum(1 for r in results if r["success"])
            console.print(f"\n[green]✅ Completed: {successful}/{len(results)} PRs reviewed[/green]")
        
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.option("--project", required=True, help="Project name")
@click.pass_context
def list_prs(ctx, project):
    """List all open PRs for a project."""
    try:
        project_config = get_project_config(project, ctx.obj["config_path"])
        if not project_config:
            console.print(f"[red]❌ Project '{project}' not found in config[/red]")
            sys.exit(1)
        
        reviewer = SmartReviewer(project_config)
        prs = reviewer.github.list_open_prs()
        
        if not prs:
            console.print(f"[yellow]No open PRs found in {project}[/yellow]")
            return
        
        table = Table(title=f"📋 Open PRs in {project}")
        table.add_column("PR #", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Author", style="green")
        table.add_column("Created", style="yellow")
        
        for pr in prs:
            table.add_row(
                str(pr["number"]),
                pr["title"][:60] + "..." if len(pr["title"]) > 60 else pr["title"],
                pr["author"],
                pr["created_at"][:10]
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--project", required=True, help="Project name")
@click.option("--pr", type=int, required=True, help="PR number")
@click.option("--repo-path", help="Path to cloned repo (optional)")
@click.pass_context
def test_llm(ctx, project, pr, repo_path):
    """Test LLM review generation without posting."""
    try:
        project_config = get_project_config(project, ctx.obj["config_path"])
        if not project_config:
            console.print(f"[red]❌ Project '{project}' not found in config[/red]")
            sys.exit(1)
        
        reviewer = SmartReviewer(project_config)
        
        console.print(f"[cyan]🧪 Testing {project_config.llm.provider} on PR #{pr}...[/cyan]")
        review_result = reviewer.review_pr(pr, repo_path)
        
        _display_review(pr, review_result)
        
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _display_review(pr_number: int, review: dict):
    """Display review results in a nice format."""
    event = review.get("event", "COMMENT")
    summary = review.get("summary", "")
    comments = review.get("comments", [])
    
    # Color based on event
    event_colors = {
        "APPROVE": "green",
        "REQUEST_CHANGES": "red",
        "COMMENT": "yellow"
    }
    color = event_colors.get(event, "white")
    
    console.print(Panel.fit(
        f"[{color}]{event}[/{color}]\n\n{summary}",
        title=f"📝 Review for PR #{pr_number}"
    ))
    
    if comments:
        console.print(f"\n[bold]💬 Comments ({len(comments)}):[/bold]")
        for i, comment in enumerate(comments[:10], 1):
            console.print(f"\n{i}. [cyan]{comment['path']}:{comment['line']}[/cyan]")
            console.print(f"   {comment['body']}")
        
        if len(comments) > 10:
            console.print(f"\n[yellow]... and {len(comments) - 10} more comments[/yellow]")


if __name__ == "__main__":
    cli()
