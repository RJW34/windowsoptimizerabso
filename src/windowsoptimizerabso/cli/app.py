"""``winopt`` command line.

Everything here is read-only. There is no code path from this module to a mutation: the commands
that used to change a machine are declared in :data:`WITHDRAWN_COMMANDS` and refuse with
:attr:`ExitCode.CONTAINED`, and the legacy implementations they used to call are quarantined under
``windowsoptimizerabso.legacy`` behind a separate opt-in.

Commands the CLI contract still owes (``plan``, ``apply``, ``verify``, ``rollback``, ``profiles``,
``recover``) arrive with the planner and executor. They are deliberately absent rather than
stubbed: a command that exists but does nothing is how the baseline ended up printing
"Rollback complete."
"""

from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .. import __version__
from ..inspection import system_info
from ..safety import ALLOW_LEGACY_ENV, ALLOW_MUTATION_ENV, containment_status
from .exit_codes import DESCRIPTIONS, ExitCode

app = typer.Typer(
    name="winopt",
    help="Windows state planner. Read-only by default; every change is planned, journalled and reversible.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()

#: Commands withdrawn in Phase 0, and what an operator should reach for instead. Keeping them
#: present-but-refusing is deliberate: `winopt gaming` printing "no such command" would leave a
#: user who read the old README guessing, while this tells them why it is gone and where it went.
WITHDRAWN_COMMANDS: dict[str, tuple[str, str]] = {
    "optimize": (
        "BASE-003, BASE-007",
        "It called a backup method that does not exist, then mutated without a durable record.",
    ),
    "gaming": (
        "BASE-007, GAM-001..GAM-007",
        "It bundled unrelated changes -- Game Mode, DVR, GPU scheduling, HDCP, TDR timeouts -- "
        "behind one flag, several of which are folklore rather than documented behaviour.",
    ),
    "privacy": (
        "BASE-007, PRV-002, PRV-007",
        "It disabled scheduled tasks with no pre-state capture, and wrote HKCU settings that may "
        "have landed in the elevated account rather than the interactive user's hive.",
    ),
    "cleanup": (
        "BASE-007, CLN-001, CLN-002",
        "It reported success despite deletion errors, and labelled irreversible deletion 'safe'.",
    ),
    "visual": (
        "BASE-008, VIS-001, VIS-002",
        "Presets bypassed the engine entirely: no confirmation, no backup, no session record, and "
        "the child operations' rollback data was discarded.",
    ),
    "rollback": (
        "BASE-004, CORE-010",
        "It reported success without restoring anything at all. The command returns once it can "
        "restore exact captured state and verify the restoration.",
    ),
}


def _fail(code: ExitCode, title: str, body: str) -> None:
    console.print(Panel.fit(body, title=title, border_style="red"))
    raise typer.Exit(int(code))


def _register_withdrawn(name: str, defects: str, why: str) -> None:
    @app.command(name=name, help=f"[withdrawn] see `winopt doctor` ({defects})")
    def _withdrawn() -> None:  # pragma: no cover - body is exercised via CliRunner in tests
        _fail(
            ExitCode.CONTAINED,
            "Refused",
            f"[bold red]`winopt {name}` has been withdrawn.[/]\n\n"
            f"{why}\n\n"
            f"[bold]Defects:[/] {defects}\n"
            "[bold]Status:[/] docs/remediation/WORK_LEDGER.md\n\n"
            "Nothing was changed. `winopt inspect` and `winopt doctor` are read-only and work now.",
        )


for _name, (_defects, _why) in WITHDRAWN_COMMANDS.items():
    _register_withdrawn(_name, _defects, _why)


@app.command()
def version() -> None:
    """Print the version."""
    console.print(f"winopt {__version__}")


@app.command()
def inspect(
    as_json: bool = typer.Option(False, "--json", help="Emit stable JSON for automation."),
    include_identifiers: bool = typer.Option(
        False,
        "--include-identifiers",
        help="Include hostname and registered owner. Off by default; reports get shared.",
    ),
) -> None:
    """Show what this machine actually looks like. Read-only, no admin required."""
    facts = system_info.gather()

    if as_json:
        console.print_json(json.dumps(facts.to_dict(include_identifiers=include_identifiers)))
        raise typer.Exit(int(ExitCode.SUCCESS))

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Property", style="dim")
    table.add_column("Value", style="bold")

    table.add_row("OS", f"{facts.os.product_name or facts.os.system} {facts.os.release}")
    if facts.os.display_version or facts.os.build:
        table.add_row("Version", f"{facts.os.display_version or '?'} (build {facts.os.build or '?'})")
    if facts.os.edition:
        table.add_row("Edition", facts.os.edition)
    table.add_row("Machine", facts.hostname if include_identifiers else f"fingerprint {facts.machine_fingerprint}")
    table.add_row("Elevated", "[green]yes[/]" if facts.is_admin else "no")

    if facts.cpu:
        cores = f"{facts.cpu.cores_physical or '?'} physical / {facts.cpu.cores_logical or '?'} logical"
        table.add_row("CPU", f"{facts.cpu.model} ({cores}, {facts.cpu.architecture})")
    if facts.memory:
        table.add_row(
            "Memory",
            f"{facts.memory.total_gb:.1f} GB total, {facts.memory.available_gb:.1f} GB available "
            f"({facts.memory.percent_used:.0f}% used)",
        )
    for disk in facts.disks:
        table.add_row(
            f"Disk {disk.mountpoint}",
            f"{disk.free_gb:.1f} GB free of {disk.total_gb:.1f} GB ({disk.percent_used:.0f}% used)",
        )
    if facts.uptime_hours is not None:
        table.add_row("Uptime", f"{facts.uptime_hours:.1f} h")

    console.print(Panel.fit("[bold cyan]Machine[/]"))
    console.print(table)

    if facts.collection_notes:
        console.print("\n[bold]Not collected:[/]")
        for note in facts.collection_notes:
            console.print(f"  [dim]-[/] {note}")

    raise typer.Exit(int(ExitCode.SUCCESS))


@app.command()
def doctor(
    as_json: bool = typer.Option(False, "--json", help="Emit stable JSON for automation."),
) -> None:
    """Report whether this environment can plan, and whether mutation is contained.

    Exits non-zero when the environment could not run a plan, so CI and scripts can gate on it.
    """
    facts = system_info.gather()
    containment = containment_status()

    checks: list[tuple[str, bool, str]] = [
        (
            "python version",
            system_info.python_supported(),
            f"{facts.python_version} (3.10+ required)",
        ),
        (
            "platform",
            facts.is_windows,
            f"{facts.os.system}: planning works anywhere, applying requires Windows",
        ),
        (
            "elevation",
            facts.is_admin,
            "elevated: machine-scoped operations could be applied"
            if facts.is_admin
            else "not elevated: inspection and planning are fine, applying machine-scoped "
            "operations is not",
        ),
        (
            "containment",
            not containment.legacy_mutation_enabled,
            containment.summary,
        ),
    ]

    if as_json:
        console.print_json(json.dumps({
            "version": __version__,
            "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
            "containment": containment.to_dict(),
            "system": facts.to_dict(),
            "exit_codes": {c.name: {"code": int(c), "meaning": DESCRIPTIONS[c]} for c in ExitCode},
        }))
    else:
        console.print(Panel.fit(f"[bold cyan]winopt doctor[/] {__version__}"))
        table = Table(show_header=True)
        table.add_column("Check")
        table.add_column("", width=3)
        table.add_column("Detail")
        for name, ok, detail in checks:
            table.add_row(name, "[green]ok[/]" if ok else "[yellow]![/]", detail)
        console.print(table)

        console.print(f"\n[bold]Mutation:[/] {containment.summary}")
        if not containment.mutation_enabled:
            console.print(
                f"[dim]All mutating commands are withdrawn while the transactional core is being "
                f"built. {ALLOW_MUTATION_ENV} and {ALLOW_LEGACY_ENV} exist for disposable Windows "
                f"VMs only.[/]"
            )

    # Being non-Windows or unelevated is not an error for a read-only tool, so neither fails the
    # command. An unsupported interpreter does: nothing downstream is expected to work.
    if not system_info.python_supported():
        raise typer.Exit(int(ExitCode.UNSUPPORTED))
    raise typer.Exit(int(ExitCode.SUCCESS))


@app.command(name="exit-codes")
def exit_codes(
    as_json: bool = typer.Option(False, "--json", help="Emit stable JSON for automation."),
) -> None:
    """List the documented exit codes and what they mean."""
    if as_json:
        console.print_json(json.dumps({c.name: {"code": int(c), "meaning": DESCRIPTIONS[c]} for c in ExitCode}))
        raise typer.Exit(int(ExitCode.SUCCESS))

    table = Table(show_header=True)
    table.add_column("Code", justify="right")
    table.add_column("Name")
    table.add_column("Meaning")
    for code in ExitCode:
        table.add_row(str(int(code)), code.name, DESCRIPTIONS[code])
    console.print(table)
    raise typer.Exit(int(ExitCode.SUCCESS))


def main(argv: Optional[list[str]] = None) -> None:
    """Console-script entry point."""
    app(args=argv)


if __name__ == "__main__":  # pragma: no cover
    main()
