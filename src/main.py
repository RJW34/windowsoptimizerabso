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

from .safety import ContainmentStatus, containment_status
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


#: Exit code used when a command is refused because the repository is contained (gate G0).
EXIT_CONTAINED = 3


def refuse_mutating_command(command: str, replacement: str) -> None:
    """Refuse a legacy mutating command and explain what replaces it.

    Every mutating command in this CLI predates the transactional core: it has no exact pre-state
    capture, no durable journal, and no verified rollback. Until those exist, these commands are
    unavailable rather than merely discouraged (gate G0). The underlying module code is still
    guarded independently by ``safety.guard_mutation``; this is the outer, operator-facing layer.
    """
    status: ContainmentStatus = containment_status()
    console.print(
        Panel.fit(
            f"[bold red]`winopt {command}` is disabled.[/]\n\n"
            "This command changes the machine through the legacy code path, which has no exact\n"
            "pre-state capture, no transaction journal, and no verified rollback. Running it\n"
            "could leave the system in a state this tool cannot restore.\n\n"
            f"[bold]Containment:[/] {status.summary}\n"
            f"[bold]Instead:[/] {replacement}\n\n"
            "Tracking: docs/remediation/WORK_LEDGER.md (BASE-003, BASE-004, BASE-007, BASE-008)",
            title="Refused",
            border_style="red",
        )
    )
    raise typer.Exit(EXIT_CONTAINED)


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
    refuse_mutating_command(
        "optimize",
        "`winopt analyze` and `winopt info` remain available and are read-only.",
    )

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
    refuse_mutating_command(
        "gaming",
        "`winopt analyze --category gaming` lists what the legacy module would have changed.",
    )

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
    refuse_mutating_command(
        "privacy",
        "`winopt analyze --category privacy` lists what the legacy module would have changed.",
    )

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
    refuse_mutating_command(
        "cleanup",
        "`winopt analyze --category cleanup` lists what the legacy module would have removed.",
    )

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

    # Find and load session.
    # BASE-005: the condition was inverted, so a name that already ended in ".json" had a second
    # ".json" appended and could never be found. Candidates are now tried in order, most explicit
    # first, and a name containing a path separator is rejected rather than escaping backup_dir.
    if "/" in session or "\\" in session or session in {".", ".."}:
        console.print(f"[red]Invalid session name: {session}[/]")
        raise typer.Exit(1)

    candidates = [
        backup_dir / session,
        backup_dir / f"{session}.json",
        backup_dir / f"session_{session}.json",
    ]
    session_path = next((c for c in candidates if c.exists()), None)

    if session_path is None:
        console.print(f"[red]Session not found: {session}[/]")
        raise typer.Exit(1)

    engine = get_engine()
    results = engine.load_session(session_path)

    console.print(f"Loaded session with {len(results)} operations.")

    # BASE-004: this printed "Rollback complete." while doing nothing at all. Reporting a
    # rollback that did not happen is the most dangerous defect in the baseline, because it
    # invites the operator to trust an unreverted machine. It now fails loudly instead.
    console.print(
        Panel.fit(
            "[bold red]Rollback is not implemented.[/]\n\n"
            f"The session file was read and contains {len(results)} recorded operations, but this\n"
            "build cannot restore them: the legacy session format records an operation name and a\n"
            "boolean, not the exact prior state, and it is not connected to the engine's rollback\n"
            "functions (BASE-004, BASE-006, CORE-010).\n\n"
            "Nothing was changed. Do not treat this session as reverted.",
            title="Refused",
            border_style="red",
        )
    )
    raise typer.Exit(EXIT_CONTAINED)


@app.command()
def visual(
    preset: str = typer.Option(None, "--preset", "-p", help="Apply preset: performance, balanced, appearance"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be done"),
):
    """Optimize visual effects"""
    setup_logging()

    module = VisualModule(dry_run=dry_run)

    if preset:
        # BASE-008: presets bypassed the engine entirely -- no confirmation, no backup, no session
        # record, no rollback. The read-only analysis below is unaffected.
        refuse_mutating_command(
            "visual --preset",
            "`winopt visual` with no options shows the current visual-effects state.",
        )

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
