"""Proof for gate G0: nothing reachable in this repository can mutate a host.

These tests are the evidence behind the `fixed` status of BASE-004, BASE-007, BASE-008, BASE-010,
SEC-001, SEC-002 and BAK-011 in ``docs/remediation/WORK_LEDGER.md``.

They run on any platform. On non-Windows they additionally prove the platform gate; on Windows they
prove the environment gate, because neither opt-in variable is set in a test process.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src import safety  # noqa: E402
from src.safety import (  # noqa: E402
    ALLOW_LEGACY_ENV,
    ALLOW_MUTATION_ENV,
    MutationBlocked,
    UntrustedExecutable,
    guard_mutation,
    guarded_run,
    resolve_trusted_executable,
)


@pytest.fixture(autouse=True)
def _contained(monkeypatch):
    """Every test starts from the contained state, whatever the ambient environment says."""
    monkeypatch.delenv(ALLOW_MUTATION_ENV, raising=False)
    monkeypatch.delenv(ALLOW_LEGACY_ENV, raising=False)


# ---------------------------------------------------------------------------
# The guard itself
# ---------------------------------------------------------------------------

def test_mutation_is_blocked_by_default():
    with pytest.raises(MutationBlocked):
        guard_mutation("write HKLM value")


def test_blocked_message_names_every_failing_condition(monkeypatch):
    monkeypatch.setattr(safety, "is_windows", lambda: True)
    with pytest.raises(MutationBlocked) as excinfo:
        guard_mutation("disable service", legacy=True)
    message = str(excinfo.value)
    assert ALLOW_MUTATION_ENV in message
    assert ALLOW_LEGACY_ENV in message


def test_platform_gate_holds_even_with_the_env_var_set(monkeypatch):
    """BASE-010: the opt-in must not be sufficient on a non-Windows host."""
    monkeypatch.setenv(ALLOW_MUTATION_ENV, "1")
    monkeypatch.setattr(safety, "is_windows", lambda: False)
    with pytest.raises(MutationBlocked):
        guard_mutation("write registry")


def test_legacy_mutation_needs_the_second_opt_in(monkeypatch):
    monkeypatch.setenv(ALLOW_MUTATION_ENV, "1")
    monkeypatch.setattr(safety, "is_windows", lambda: True)

    guard_mutation("ported operation")  # first opt-in is enough for ported operations

    with pytest.raises(MutationBlocked):
        guard_mutation("legacy operation", legacy=True)

    monkeypatch.setenv(ALLOW_LEGACY_ENV, "1")
    guard_mutation("legacy operation", legacy=True)  # both opt-ins: allowed


def test_containment_failures_are_not_catchable_as_exception():
    """A blocked mutation must survive the legacy tree's broad `except Exception` handlers.

    Without this, a guard would raise, a legacy handler would log "operation failed", return False,
    and execution would continue to the next operation as though the machine had merely refused.
    """
    assert not issubclass(MutationBlocked, Exception)

    def legacy_style_caller():
        try:
            guard_mutation("delete file")
            return True
        except Exception:  # noqa: BLE001 - deliberately reproducing the legacy pattern
            return False

    with pytest.raises(MutationBlocked):
        legacy_style_caller()


# ---------------------------------------------------------------------------
# Subprocess classification (fail closed on anything unrecognised)
# ---------------------------------------------------------------------------

READ_ONLY = [
    ("sc", ["query", "state=", "all"]),
    ("sc", ["qc", "DiagTrack"]),
    ("sc", ["enumdepend", "RpcSs"]),
    ("reg", ["query", r"HKLM\SOFTWARE"]),
    ("reg", ["export", r"HKLM\SOFTWARE", "out.reg", "/y"]),
    ("ipconfig", ["/displaydns"]),
    ("ipconfig", ["/all"]),
    ("netsh", ["int", "tcp", "show", "global"]),
    ("schtasks", ["/Query", "/FO", "CSV", "/V"]),
    ("powercfg", ["/list"]),
    ("powercfg", ["/getactivescheme"]),
]

MUTATING = [
    ("sc", ["config", "DiagTrack", "start=", "disabled"]),
    ("sc", ["stop", "DiagTrack"]),
    ("sc", ["delete", "DiagTrack"]),
    ("reg", ["import", "payload.reg"]),
    ("reg", ["add", r"HKLM\SOFTWARE", "/v", "X", "/d", "1"]),
    ("reg", ["delete", r"HKLM\SOFTWARE"]),
    ("ipconfig", ["/flushdns"]),
    ("ipconfig", ["/release"]),
    ("netsh", ["int", "tcp", "set", "global", "autotuninglevel=disabled"]),
    ("netsh", ["winsock", "reset"]),
    ("schtasks", ["/Change", "/TN", "T", "/Disable"]),
    ("powercfg", ["/setactive", "guid"]),
    ("cleanmgr", ["/d", "C:", "/VERYLOWDISK"]),
    ("powershell", ["-Command", "Get-Date"]),  # never classifiable: arbitrary script
    ("shutdown", ["/r", "/t", "0"]),
]


@pytest.mark.parametrize(("command", "args"), READ_ONLY)
def test_read_only_invocations_are_permitted_while_contained(command, args):
    assert safety._is_read_only(command, args) is True


@pytest.mark.parametrize(("command", "args"), MUTATING)
def test_mutating_invocations_are_refused_while_contained(command, args):
    assert safety._is_read_only(command, args) is False
    with pytest.raises(MutationBlocked):
        guarded_run([command, *args])


def test_unknown_commands_are_treated_as_mutating():
    """Fail closed: a verb nobody has classified must not be assumed harmless."""
    assert safety._is_read_only("sc", ["frobnicate"]) is False
    assert safety._is_read_only("netsh", ["int", "tcp", "reset"]) is False
    assert safety._is_read_only("totally-unknown", ["--go"]) is False


def test_guarded_run_rejects_shell_strings():
    with pytest.raises(TypeError):
        guarded_run("sc query DiagTrack")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Trusted executable resolution (SEC-001)
# ---------------------------------------------------------------------------

def test_system_binaries_resolve_under_system_root():
    resolved = resolve_trusted_executable("sc")
    assert resolved.lower().endswith("system32\\sc.exe") or resolved.lower().endswith("system32/sc.exe")
    assert str(safety.system_root()) in resolved


def test_path_is_never_consulted_for_unlisted_binaries():
    """A planted binary earlier in PATH must not become reachable."""
    for name in ["curl", "python", "cmd", "wget", "evil"]:
        with pytest.raises(UntrustedExecutable):
            resolve_trusted_executable(name)


def test_absolute_paths_outside_system_root_are_rejected():
    with pytest.raises(UntrustedExecutable):
        resolve_trusted_executable("/tmp/sc.exe")
    with pytest.raises(UntrustedExecutable):
        resolve_trusted_executable(r"C:\Users\Public\sc.exe")


def test_extra_env_names_are_validated():
    with pytest.raises(ValueError):
        guarded_run(["sc", "query"], mutating=False, extra_env={"BAD NAME": "x"})


# ---------------------------------------------------------------------------
# Legacy mutation sites are individually guarded
# ---------------------------------------------------------------------------

def test_registry_writes_are_guarded():
    from src.core.registry import RegistryManager

    manager = RegistryManager()
    with pytest.raises(MutationBlocked):
        manager.set_value(r"HKCU\Software\Test", "Value", 1)
    with pytest.raises(MutationBlocked):
        manager.delete_value(r"HKCU\Software\Test", "Value")
    with pytest.raises(MutationBlocked):
        manager.delete_key(r"HKCU\Software\Test")


def test_registry_export_stays_available_but_import_does_not():
    """Reading state must keep working while contained; writing it back must not."""
    from src.core.registry import RegistryManager

    manager = RegistryManager()
    with pytest.raises(MutationBlocked):
        manager.import_key(pathlib.Path("payload.reg"))
    assert safety._is_read_only("reg", ["export", "HKLM", "out.reg", "/y"]) is True


def test_service_mutations_are_guarded():
    from src.core.services import ServiceManager, ServiceStartType

    manager = ServiceManager()
    with pytest.raises(MutationBlocked):
        manager.set_start_type("DiagTrack", ServiceStartType.DISABLED)
    with pytest.raises(MutationBlocked):
        manager.stop_service("DiagTrack")
    with pytest.raises(MutationBlocked):
        manager.start_service("DiagTrack")


def test_restore_point_description_cannot_inject_powershell(monkeypatch, tmp_path):
    """SEC-002/BAK-011: the description must never reach a command interpreter."""
    from src.core.backup import BackupManager

    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["extra_env"] = kwargs.get("extra_env") or {}
        return safety.RunResult(argv=tuple(argv), returncode=0, stdout="", stderr="", timed_out=False)

    monkeypatch.setattr("src.core.backup.guarded_run", fake_run)

    manager = BackupManager(backup_dir=tmp_path / "backups")
    hostile = 'x"; Remove-Item C:\\ -Recurse -Force; "'
    assert manager.create_system_restore_point(hostile) is True

    joined = " ".join(captured["argv"])
    assert "Remove-Item" not in joined, "hostile description reached the command line"
    assert hostile in captured["extra_env"].values(), "description should travel in the environment"
    assert "-NoProfile" in captured["argv"]


def test_restore_point_description_rejects_newlines(tmp_path):
    from src.core.backup import BackupManager

    manager = BackupManager(backup_dir=tmp_path / "backups")
    assert manager.create_system_restore_point("line1\nline2") is False
    assert manager.create_system_restore_point("") is False
    assert manager.create_system_restore_point("x" * 256) is False


def test_file_restore_rejects_backup_with_no_recorded_origin(tmp_path):
    """BAK-007: Path("") is truthy, so the old guard never fired."""
    from datetime import datetime

    from src.core.backup import BackupEntry, BackupManager, BackupType

    manager = BackupManager(backup_dir=tmp_path / "backups")
    entry = BackupEntry(
        id="x",
        type=BackupType.FILE,
        description="orphan",
        path=tmp_path / "backup.bin",
        created_at=datetime.now(),
        size_bytes=0,
        metadata={},
    )
    assert manager.restore_file(entry) is False


# ---------------------------------------------------------------------------
# CLI level (BASE-004, BASE-007, BASE-008)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "argv",
    [
        ["optimize", "-y"],
        ["gaming", "-y"],
        ["privacy", "-y"],
        ["cleanup", "-y"],
        ["visual", "--preset", "performance"],
    ],
)
def test_mutating_cli_commands_exit_with_the_contained_code(argv):
    from typer.testing import CliRunner

    from src.main import EXIT_CONTAINED, app

    result = CliRunner().invoke(app, argv)
    assert result.exit_code == EXIT_CONTAINED, result.output


def test_rollback_no_longer_claims_success(tmp_path, monkeypatch):
    """BASE-004: the baseline printed 'Rollback complete.' without rolling anything back."""
    import json

    from typer.testing import CliRunner

    from src.main import EXIT_CONTAINED, app

    backup_dir = tmp_path / ".winopt" / "backups"
    backup_dir.mkdir(parents=True)
    session = backup_dir / "session_20260101_000000.json"
    session.write_text(json.dumps({
        "timestamp": "2026-01-01T00:00:00",
        "level": "SAFE",
        "dry_run": False,
        "results": [{
            "success": True, "module": "privacy", "operation": "disable_telemetry",
            "message": "ok", "details": {}, "rollback_data": {"x": 1},
            "timestamp": "2026-01-01T00:00:00",
        }],
    }))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))

    result = CliRunner().invoke(app, ["rollback", session.name])
    assert result.exit_code == EXIT_CONTAINED, result.output
    assert "Rollback complete" not in result.output
    assert "not implemented" in result.output.lower()
