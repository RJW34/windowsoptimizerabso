"""
Containment layer: the single choke point through which any host mutation must pass.

This module exists because of gate G0 in ``manifests/acceptance_gate_matrix.csv``: until the
transactional executor, exact-state journal, verification layer, and proven rollback exist, no
command in this repository may change a real machine.

The design is default-deny on four independent axes. All four must pass:

1. ``WINOPT_ALLOW_MUTATION=1`` must be set in the process environment.
2. The platform must be Windows.
3. Reaching *legacy* (unported, unjournaled) mutation additionally requires
   ``WINOPT_UNSAFE_LEGACY=1``.
4. A subprocess invocation must either match the read-only allowlist, or be run by a caller that
   has already passed 1-3 and declares the call mutating.

Anything unrecognised is treated as mutating. See ``docs/remediation/DECISION_LOG.md`` D-002 for
why this is an environment variable rather than a CLI flag.
"""

from __future__ import annotations

import os
import platform
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

ALLOW_MUTATION_ENV = "WINOPT_ALLOW_MUTATION"
ALLOW_LEGACY_ENV = "WINOPT_UNSAFE_LEGACY"

#: Subprocess timeout used when a caller does not supply one. No call is allowed to run unbounded.
DEFAULT_TIMEOUT_SECONDS = 30


class SafetyError(BaseException):
    """Base class for containment failures.

    Deliberately derived from :class:`BaseException`, not :class:`Exception`, so that the broad
    ``except Exception: return False`` handlers throughout the legacy tree cannot swallow a
    containment refusal and turn it into an ordinary failed result. A blocked mutation is a
    control-flow event like :class:`KeyboardInterrupt`, not a recoverable error: if it were
    catchable, a caller could log "operation failed" and carry on to the next operation, and the
    operator would never learn that containment -- rather than the machine -- refused the change.
    """


class MutationBlocked(SafetyError):
    """Raised when an operation that would change the host is attempted while containment is on."""


class UnsupportedPlatform(SafetyError):
    """Raised when a Windows-only operation is attempted elsewhere."""


class UntrustedExecutable(SafetyError):
    """Raised when a subprocess target cannot be resolved to a trusted absolute path."""


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def is_windows() -> bool:
    return platform.system() == "Windows"


def mutation_enabled() -> bool:
    """True when the operator has explicitly opted in to host mutation on a Windows host."""
    return _env_flag(ALLOW_MUTATION_ENV) and is_windows()


def legacy_mutation_enabled() -> bool:
    """True when the operator has additionally opted in to *unported legacy* mutation.

    Legacy operations have no pre-state capture, no journal, and no verified rollback. This flag
    exists only so the legacy tree can be exercised inside a disposable Windows VM during porting.
    """
    return mutation_enabled() and _env_flag(ALLOW_LEGACY_ENV)


@dataclass(frozen=True)
class ContainmentStatus:
    """Snapshot of the containment state, for ``winopt doctor``."""

    platform: str
    is_windows: bool
    allow_mutation_env: bool
    allow_legacy_env: bool
    mutation_enabled: bool
    legacy_mutation_enabled: bool

    @property
    def summary(self) -> str:
        if self.legacy_mutation_enabled:
            return "LEGACY MUTATION ENABLED - unjournaled, unverified, no rollback"
        if self.mutation_enabled:
            return "mutation enabled for ported operations only"
        return "contained (read-only)"

    def to_dict(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "is_windows": self.is_windows,
            f"{ALLOW_MUTATION_ENV}": self.allow_mutation_env,
            f"{ALLOW_LEGACY_ENV}": self.allow_legacy_env,
            "mutation_enabled": self.mutation_enabled,
            "legacy_mutation_enabled": self.legacy_mutation_enabled,
            "summary": self.summary,
        }


def containment_status() -> ContainmentStatus:
    return ContainmentStatus(
        platform=platform.system(),
        is_windows=is_windows(),
        allow_mutation_env=_env_flag(ALLOW_MUTATION_ENV),
        allow_legacy_env=_env_flag(ALLOW_LEGACY_ENV),
        mutation_enabled=mutation_enabled(),
        legacy_mutation_enabled=legacy_mutation_enabled(),
    )


def _blocked_message(description: str, *, legacy: bool) -> str:
    lines = [
        f"Refusing to mutate the host: {description}",
        "",
        "This repository is under remediation and is contained by default "
        "(see docs/remediation/02_IMPLEMENTATION_SEQUENCE.md, gate G0).",
    ]
    if not is_windows():
        lines.append(f"  - platform is {platform.system()}, not Windows")
    if not _env_flag(ALLOW_MUTATION_ENV):
        lines.append(f"  - {ALLOW_MUTATION_ENV} is not set")
    if legacy and not _env_flag(ALLOW_LEGACY_ENV):
        lines.append(
            f"  - {ALLOW_LEGACY_ENV} is not set; this is a legacy operation with no pre-state "
            "capture, no journal, and no verified rollback"
        )
    lines.append("")
    lines.append("Do not set these on a machine you care about. Use a disposable Windows VM.")
    return "\n".join(lines)


def guard_mutation(description: str, *, legacy: bool = False) -> None:
    """Raise :class:`MutationBlocked` unless host mutation is explicitly enabled.

    Args:
        description: What the caller is about to change, for the operator-facing error.
        legacy: True for operations in the unported ``legacy`` tree, which require the second
            opt-in flag on top of the first.
    """
    enabled = legacy_mutation_enabled() if legacy else mutation_enabled()
    if enabled:
        logger.warning(f"MUTATION ALLOWED (legacy={legacy}): {description}")
        return
    raise MutationBlocked(_blocked_message(description, legacy=legacy))


def require_windows(description: str) -> None:
    """Raise :class:`UnsupportedPlatform` when a Windows-only operation runs elsewhere.

    Fails closed rather than silently returning a falsy result, so that a non-Windows run can never
    be mistaken for a successful no-op (defect BASE-010).
    """
    if not is_windows():
        raise UnsupportedPlatform(
            f"{description} requires Windows; running on {platform.system()}"
        )


# ---------------------------------------------------------------------------
# Trusted executable resolution (defect SEC-001)
# ---------------------------------------------------------------------------

#: System binaries this codebase is allowed to invoke, resolved under %SystemRoot%\System32
#: rather than through PATH, so that a planted sc.exe / reg.exe earlier in PATH cannot be used.
_SYSTEM32_BINARIES = {
    "cleanmgr": "cleanmgr.exe",
    "defrag": "defrag.exe",
    "dism": "Dism.exe",
    "ipconfig": "ipconfig.exe",
    "netsh": "netsh.exe",
    "powercfg": "powercfg.exe",
    "reg": "reg.exe",
    "sc": "sc.exe",
    "schtasks": "schtasks.exe",
    "shutdown": "shutdown.exe",
    "wevtutil": "wevtutil.exe",
}

_POWERSHELL_RELATIVE = Path("WindowsPowerShell") / "v1.0" / "powershell.exe"


def system_root() -> Path:
    # noqa: SIM112 below -- these are the names Windows itself sets, and its environment lookup is
    # case-insensitive, so upper-casing them would be a cosmetic change with no effect.
    return Path(
        os.environ.get("SystemRoot")  # noqa: SIM112
        or os.environ.get("WINDIR")
        or r"C:\Windows"
    )


def resolve_trusted_executable(name: str) -> str:
    """Map a bare command name to a trusted absolute path under %SystemRoot%.

    Raises:
        UntrustedExecutable: if the name is not on the allowlist. PATH is never consulted.
    """
    if os.path.isabs(name):
        # An absolute path is accepted only if it is inside %SystemRoot%.
        candidate = Path(name)
        try:
            candidate.relative_to(system_root())
        except ValueError as exc:
            raise UntrustedExecutable(f"Executable outside %SystemRoot%: {name}") from exc
        return str(candidate)

    key = name.lower().removesuffix(".exe")
    system32 = system_root() / "System32"
    if key in _SYSTEM32_BINARIES:
        return str(system32 / _SYSTEM32_BINARIES[key])
    if key == "powershell":
        return str(system32 / _POWERSHELL_RELATIVE)
    raise UntrustedExecutable(
        f"{name!r} is not an allowlisted system binary. Add it to safety._SYSTEM32_BINARIES "
        "with a justification if it is genuinely needed."
    )


# ---------------------------------------------------------------------------
# Read-only subprocess classification
# ---------------------------------------------------------------------------

def _is_read_only(command: str, args: Sequence[str]) -> bool:
    """Classify an invocation as observably read-only.

    Conservative by construction: an invocation is read-only only if it is recognised as such.
    Anything unknown is mutating. ``powershell`` is never read-only, because the argument is an
    arbitrary script this classifier cannot reason about.
    """
    lowered = [a.lower() for a in args]
    first = lowered[0] if lowered else ""

    if command == "sc":
        # sc.exe accepts an optional \\server prefix before the verb.
        verb = lowered[1] if first.startswith("\\\\") and len(lowered) > 1 else first
        return verb in {"query", "queryex", "qc", "qdescription", "enumdepend", "getdisplayname",
                        "getkeyname", "showsid", "qfailure", "qtriggerinfo", "sdshow"}
    if command == "reg":
        return first in {"query", "export", "compare"}
    if command == "ipconfig":
        return first in {"", "/all", "/displaydns", "/allcompartments"}
    if command == "netsh":
        # netsh contexts are `netsh <context> [subcontext] <verb> ...`; only show/dump observe.
        return any(token in {"show", "dump"} for token in lowered)
    if command == "schtasks":
        return first == "/query"
    if command == "powercfg":
        return first in {"/list", "/l", "/query", "/q", "/getactivescheme", "/availablesleepstates",
                         "/a", "/devicequery"}
    if command == "wevtutil":
        return first in {"el", "gl", "gli", "qe", "epl"}
    if command == "defrag":
        return "/a" in lowered  # /A is analyse-only
    return False


@dataclass(frozen=True)
class RunResult:
    """Outcome of a guarded subprocess call.

    Unlike ``subprocess.CompletedProcess`` this records whether the call timed out, so a caller
    can distinguish "the command reported failure" from "the command never finished" (defect
    CORE-016: a boolean cannot represent that difference).
    """

    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def guarded_run(
    argv: Sequence[str],
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    legacy: bool = True,
    mutating: bool | None = None,
    cwd: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> RunResult:
    """Run a system binary under containment.

    Every subprocess in this codebase goes through here. The call is refused when it would mutate
    the host and mutation is not enabled; read-only calls are always permitted, on the grounds that
    inspection must work in the contained state.

    Args:
        argv: Command and arguments. Never a string, never ``shell=True``.
        timeout: Hard timeout in seconds.
        legacy: Whether this call belongs to the unported legacy tree (requires the second opt-in).
        mutating: Force the classification instead of inferring it. Pass ``False`` only for calls
            proven not to change state.
        cwd: Working directory. Defaults to ``%SystemRoot%`` on Windows so that a poisoned current
            directory cannot influence binary or DLL resolution.
        extra_env: Additional environment variables for the child. This is the supported way to
            pass *data* to a command without putting it on a command line where a shell or a
            command interpreter could re-parse it (defect SEC-002).

    Raises:
        UntrustedExecutable: the target is not an allowlisted system binary.
        MutationBlocked: the call would mutate and containment is active.
    """
    if not argv:
        raise ValueError("guarded_run requires a non-empty argument vector")
    if isinstance(argv, (str, bytes)):
        raise TypeError("guarded_run takes an argument vector, not a shell string")

    command = str(argv[0]).lower().removesuffix(".exe")
    args = [str(a) for a in argv[1:]]

    read_only = (not mutating) if mutating is not None else _is_read_only(command, args)
    if not read_only:
        guard_mutation(f"{command} {' '.join(args)}".strip(), legacy=legacy)

    executable = resolve_trusted_executable(str(argv[0]))
    resolved = [executable, *args]

    # A constrained environment: the child inherits nothing it does not need, and cannot be steered
    # by PATH, PATHEXT or PowerShell profile variables it might otherwise pick up.
    env = {
        "SystemRoot": str(system_root()),
        "windir": str(system_root()),  # noqa: SIM112 - the actual Windows name
        "PATH": str(system_root() / "System32"),
        "TEMP": os.environ.get("TEMP", str(system_root() / "Temp")),
        "TMP": os.environ.get("TMP", str(system_root() / "Temp")),
    }
    if "SystemDrive" in os.environ:  # noqa: SIM112 - the actual Windows name
        env["SystemDrive"] = os.environ["SystemDrive"]  # noqa: SIM112
    if extra_env:
        for key, value in extra_env.items():
            if not key.isidentifier():
                raise ValueError(f"Invalid environment variable name: {key!r}")
            env[key] = value

    child_env: dict[str, str] | None
    if is_windows():
        child_env = env
    elif extra_env:
        child_env = {**os.environ, **extra_env}
    else:
        child_env = None

    try:
        completed = subprocess.run(  # noqa: S603 - argv is allowlisted and never shell-interpreted
            resolved,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(cwd) if cwd else (str(system_root()) if is_windows() else None),
            env=child_env,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error(f"Timed out after {timeout}s: {' '.join(resolved)}")
        return RunResult(
            argv=tuple(resolved),
            returncode=None,
            stdout=exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
            stderr=exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
            timed_out=True,
        )
    except FileNotFoundError as exc:
        raise UntrustedExecutable(f"Executable not found: {executable}") from exc

    return RunResult(
        argv=tuple(resolved),
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        timed_out=False,
    )
