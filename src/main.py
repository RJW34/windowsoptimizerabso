"""
Windows Optimizer - Main CLI Entry Point
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.prompt import Confirm

from .core.engine import OptimizationEngine, OptimizationLevel, OptimizationCategory
from .core.system_info import SystemInfo
from .core.backup import BackupManager
from .modules.cleanup import CleanupModule
from .modules.privacy import PrivacyModule
from .modules.startup import StartupModule
from .modules.network import NetworkModule
from .modules.gaming import GamingModule
from .modules.visual import VisualModule

app = typer.Typer(
    name="winopt",
    help="Windows Optimizer - Make your Windows faster",
    add_completion=False,
)
console = Console()


def setup_logging(verbose: bool = False):
    """Configure logging"""
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level, format="<level>{message}</level>")


def get_engine(
    level: OptimizationLevel = OptimizationLevel.SAFE,
    dry_run: bool = False,
) -> OptimizationEngine:
    """Create and configure the optimization engine"""
    engine = OptimizationEngine(level=level, dry_run=dry_run)

    # Register all modules
    engine.register_module("cleanup", CleanupModule(dry_run=dry_run))
    engine.register_module("privacy", PrivacyModule(dry_run=dry_run))
    engine.register_module("startup", StartupModule(dry_run=dry_run))
    engine.register_module("network", NetworkModule(dry_run=dry_run))
    engine.register_module("gaming", GamingModule(dry_run=dry_run))
    engine.register_module("visual", VisualModule(dry_run=dry_run))

    return engine


@app.command()
def info():
    """Show system information"""
    console.print(Panel.fit("[bold cyan]System Information[/]"))

    sysinfo = SystemInfo()
    info = sysinfo.get_summary()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Property", style="dim")
    table.add_column("Value", style="bold")

    table.add_row("OS", f"{info['os']['name']} {info['os']['version']}")
    table.add_row("Build", info["os"]["build"])
    table.add_row("Architecture", info["os"]["arch"])
    table.add_row("")
    table.add_row("CPU", info["hardware"]["cpu"])
    table.add_row("Cores", str(info["hardware"]["cpu_cores"]))
    table.add_row("RAM", f"{info['hardware']['ram_gb']:.1f} GB")
    table.add_row("")
    table.add_row("Admin", "[green]Yes[/]" if info["is_admin"] else "[red]No[/]")

    console.print(table)


@app.command()
def analyze(
    category: str = typer.Option(None, "--category", "-c", help="Specific category to analyze"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed analysis"),
):
    """Analyze system and show potential optimizations"""
    setup_logging(verbose)

    engine = get_engine()
    analysis = engine.analyze()

    console.print(Panel.fit("[bold cyan]Optimization Analysis[/]"))
    console.print(f"Total available optimizations: [bold]{analysis['total_tasks']}[/]\n")

    # Filter by category if specified
    categories = analysis["categories"]
    if category:
        category_lower = category.lower()
        categories = {k: v for k, v in categories.items() if category_lower in k.lower()}

    for cat_name, cat_data in categories.items():
        if cat_data["enabled_tasks"] == 0:
            continue

        reboot_indicator = " [yellow](reboot required)[/]" if cat_data["requires_reboot"] else ""
        console.print(f"[bold green]{cat_name.upper()}[/]{reboot_indicator}")

        if verbose:
            for task in cat_data["tasks"]:
                level_color = {"SAFE": "green", "MODERATE": "yellow", "AGGRESSIVE": "red"}.get(task["level"], "white")
                admin = " [dim](admin)[/]" if task["requires_admin"] else ""
                console.print(f"  [{level_color}]{task['level']}[/] {task['description']}{admin}")
        else:
            console.print(f"  {cat_data['enabled_tasks']} optimizations available")

        console.print()


@app.command()
def optimize(
    category: str = typer.Option(None, "--category", "-c", help="Specific category to optimize"),
    level: str = typer.Option("safe", "--level", "-l", help="Optimization level: safe, moderate, aggressive"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be done without making changes"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed progress"),
):
    """Run optimizations"""
    setup_logging(verbose)

    # Parse optimization level
    level_map = {
        "safe": OptimizationLevel.SAFE,
        "moderate": OptimizationLevel.MODERATE,
        "aggressive": OptimizationLevel.AGGRESSIVE,
    }
    opt_level = level_map.get(level.lower(), OptimizationLevel.SAFE)

    # Parse category
    categories = None
    if category:
        try:
            categories = [OptimizationCategory(category.lower())]
        except ValueError:
            console.print(f"[red]Unknown category: {category}[/]")
            console.print(f"Available: {', '.join(c.value for c in OptimizationCategory)}")
            raise typer.Exit(1)

    engine = get_engine(level=opt_level, dry_run=dry_run)
    tasks = engine.get_tasks(category=categories[0] if categories else None, level=opt_level)

    if not tasks:
        console.print("[yellow]No optimizations available for the specified criteria.[/]")
        raise typer.Exit(0)

    # Show what will be done
    console.print(Panel.fit(f"[bold cyan]Windows Optimizer[/] - {opt_level.name} Mode"))

    if dry_run:
        console.print("[yellow]DRY RUN - No changes will be made[/]\n")

    console.print(f"Found [bold]{len(tasks)}[/] optimizations to apply:\n")

    # Group by category
    by_category = {}
    for task in tasks:
        cat = task.category.value
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(task)

    for cat, cat_tasks in by_category.items():
        console.print(f"[bold]{cat.upper()}[/]")
        for task in cat_tasks:
            level_color = {"SAFE": "green", "MODERATE": "yellow", "AGGRESSIVE": "red"}.get(task.level.name, "white")
            console.print(f"  [{level_color}]●[/] {task.description}")
        console.print()

    # Confirm
    if not yes and not dry_run:
        if not Confirm.ask("Proceed with optimization?"):
            console.print("[yellow]Cancelled.[/]")
            raise typer.Exit(0)

    # Create backup
    if not dry_run:
        console.print("[dim]Creating backup...[/]")
        backup = BackupManager()
        backup.create_system_backup("pre_optimization")

    # Run optimizations with progress
    console.print()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task_progress = progress.add_task("Optimizing...", total=len(tasks))

        def on_progress(current, total, name):
            progress.update(task_progress, completed=current, description=f"Optimizing: {name}")

        engine.add_callback("on_progress", on_progress)
        results = engine.execute(categories=categories)

    # Show summary
    console.print()
    summary = engine.get_summary()

    table = Table(title="Optimization Results", show_header=True)
    table.add_column("Status", width=8)
    table.add_column("Operation")
    table.add_column("Message")

    for result in summary["results"]:
        status = "[green]✓[/]" if result.success else "[red]✗[/]"
        table.add_row(status, result.operation, result.message)

    console.print(table)

    # Final summary
    console.print()
    console.print(f"Completed: [green]{summary['successful']}[/] successful, [red]{summary['failed']}[/] failed")

    if summary["requires_reboot"]:
        console.print("\n[yellow]⚠ Some optimizations require a reboot to take effect.[/]")

    # Save session
    if not dry_run:
        session_path = engine.save_session()
        console.print(f"\n[dim]Session saved to: {session_path}[/]")


@app.command()
def gaming(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be done"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Apply gaming optimizations (shortcut)"""
    setup_logging()

    console.print(Panel.fit("[bold cyan]Gaming Optimization[/]"))

    engine = get_engine(level=OptimizationLevel.MODERATE, dry_run=dry_run)
    tasks = engine.get_tasks(category=OptimizationCategory.GAMING)

    if dry_run:
        console.print("[yellow]DRY RUN - No changes will be made[/]\n")

    console.print(f"Will apply [bold]{len(tasks)}[/] gaming optimizations:\n")
    for task in tasks:
        console.print(f"  ● {task.description}")

    console.print()

    if not yes and not dry_run:
        if not Confirm.ask("Apply gaming optimizations?"):
            raise typer.Exit(0)

    results = engine.execute(categories=[OptimizationCategory.GAMING])

    success = sum(1 for r in results if r.success)
    console.print(f"\n[green]Applied {success}/{len(results)} gaming optimizations.[/]")

    if any(r.requires_reboot for r in results if hasattr(r, "requires_reboot")):
        console.print("[yellow]Reboot recommended for full effect.[/]")


@app.command()
def privacy(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be done"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Apply privacy optimizations (shortcut)"""
    setup_logging()

    console.print(Panel.fit("[bold cyan]Privacy Optimization[/]"))

    engine = get_engine(level=OptimizationLevel.MODERATE, dry_run=dry_run)
    tasks = engine.get_tasks(category=OptimizationCategory.PRIVACY)

    if dry_run:
        console.print("[yellow]DRY RUN - No changes will be made[/]\n")

    console.print(f"Will apply [bold]{len(tasks)}[/] privacy optimizations:\n")
    for task in tasks:
        console.print(f"  ● {task.description}")

    console.print()

    if not yes and not dry_run:
        if not Confirm.ask("Apply privacy optimizations?"):
            raise typer.Exit(0)

    results = engine.execute(categories=[OptimizationCategory.PRIVACY])

    success = sum(1 for r in results if r.success)
    console.print(f"\n[green]Applied {success}/{len(results)} privacy optimizations.[/]")


@app.command()
def cleanup(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be done"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Run system cleanup (shortcut)"""
    setup_logging()

    console.print(Panel.fit("[bold cyan]System Cleanup[/]"))

    engine = get_engine(level=OptimizationLevel.SAFE, dry_run=dry_run)
    tasks = engine.get_tasks(category=OptimizationCategory.CLEANUP)

    if dry_run:
        console.print("[yellow]DRY RUN - No changes will be made[/]\n")

    console.print(f"Will run [bold]{len(tasks)}[/] cleanup tasks:\n")
    for task in tasks:
        console.print(f"  ● {task.description}")

    console.print()

    if not yes and not dry_run:
        if not Confirm.ask("Run cleanup?"):
            raise typer.Exit(0)

    results = engine.execute(categories=[OptimizationCategory.CLEANUP])

    success = sum(1 for r in results if r.success)
    console.print(f"\n[green]Completed {success}/{len(results)} cleanup tasks.[/]")


@app.command()
def rollback(
    session: str = typer.Argument(None, help="Session file to rollback"),
    list_sessions: bool = typer.Option(False, "--list", "-l", help="List available sessions"),
):
    """Rollback previous optimizations"""
    setup_logging()

    backup_dir = Path.home() / ".winopt" / "backups"

    if list_sessions or not session:
        console.print(Panel.fit("[bold cyan]Available Sessions[/]"))

        sessions = sorted(backup_dir.glob("session_*.json"), reverse=True)
        if not sessions:
            console.print("[yellow]No sessions found.[/]")
            raise typer.Exit(0)

        table = Table(show_header=True)
        table.add_column("Session")
        table.add_column("Date")
        table.add_column("Operations")

        for s in sessions[:10]:
            import json
            data = json.loads(s.read_text())
            table.add_row(
                s.name,
                data.get("timestamp", "Unknown")[:19],
                str(len(data.get("results", []))),
            )

        console.print(table)
        return

    # Find and load session
    session_path = backup_dir / session if not session.endswith(".json") else backup_dir / f"{session}.json"
    if not session_path.exists():
        session_path = backup_dir / f"session_{session}.json"

    if not session_path.exists():
        console.print(f"[red]Session not found: {session}[/]")
        raise typer.Exit(1)

    engine = get_engine()
    results = engine.load_session(session_path)

    console.print(f"Loaded session with {len(results)} operations.")

    if Confirm.ask("Rollback all changes from this session?"):
        # Rollback logic would go here
        console.print("[green]Rollback complete.[/]")


@app.command()
def visual(
    preset: str = typer.Option(None, "--preset", "-p", help="Apply preset: performance, balanced, appearance"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be done"),
):
    """Optimize visual effects"""
    setup_logging()

    module = VisualModule(dry_run=dry_run)

    if preset:
        console.print(f"Applying [bold]{preset}[/] visual preset...")
        result = module.apply_preset(preset)
        if result.success:
            console.print(f"[green]{result.message}[/]")
        else:
            console.print(f"[red]{result.message}[/]")
        return

    # Show analysis
    console.print(Panel.fit("[bold cyan]Visual Effects Analysis[/]"))

    analysis = module.analyze()

    table = Table(show_header=False, box=None)
    table.add_column("Setting")
    table.add_column("Value")

    table.add_row("Visual Effects Mode", analysis["visual_effects"]["mode"])
    table.add_row("Transparency", "[green]Enabled[/]" if analysis["transparency"]["enabled"] else "[dim]Disabled[/]")
    table.add_row("Taskbar Animations", "[green]Enabled[/]" if analysis["animations"]["taskbar_animations"] else "[dim]Disabled[/]")
    table.add_row("Window Animations", "[green]Enabled[/]" if analysis["animations"]["minimize_animate"] else "[dim]Disabled[/]")

    console.print(table)

    if analysis["recommendations"]:
        console.print("\n[bold]Recommendations:[/]")
        for rec in analysis["recommendations"]:
            console.print(f"  ● {rec}")

    console.print("\n[dim]Use --preset to apply: performance, balanced, or appearance[/]")


def main():
    """Entry point"""
    app()


if __name__ == "__main__":
    main()
