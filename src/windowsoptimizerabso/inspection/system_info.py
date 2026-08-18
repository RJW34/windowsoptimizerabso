"""Read-only inspection of the local machine.

A cleaned port of ``legacy/core/system_info.py``. Differences that matter:

- Timestamps are timezone-aware (defect SYS-004). A naive local timestamp is ambiguous across a DST
  boundary, and this data is used to reason about whether a captured pre-state is still current.
- The unused ``wmi`` import is gone (SYS-001). It was imported, feature-detected, and never called,
  which made the module look like it gathered hardware facts it never gathered.
- Reports have an explicit redaction contract (SYS-003). Hostname, MAC addresses and the registered
  owner are machine identifiers; they are omitted unless the caller opts in, and the fingerprint
  that replaces the hostname is a hash, so two reports from one machine still correlate.
- "Absent" and "could not be determined" are distinct. ``None`` means not collected on this
  platform; a missing optional dependency is reported by name in ``collection_notes`` rather than
  silently degrading the report.

Nothing in this module mutates anything, and none of it requires administrator rights.
"""

from __future__ import annotations

import hashlib
import os
import platform
import socket
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

try:  # pragma: no cover - exercised by the dependency-missing path in tests
    import psutil

    HAS_PSUTIL = True
except ImportError:  # pragma: no cover
    psutil = None
    HAS_PSUTIL = False

# typeshed gates every winreg attribute behind sys.platform == "win32", so type checking this
# module on Linux reports the whole API as missing. The `attr-defined` ignores below are that, not
# a real absence: every use is guarded by HAS_WINREG at runtime.
try:  # pragma: no cover - Windows only
    import winreg

    HAS_WINREG = True
except ImportError:
    winreg = None  # type: ignore[assignment]
    HAS_WINREG = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def fingerprint(value: str) -> str:
    """Stable, non-reversing identifier for a machine-identifying string.

    Two reports from the same machine share a fingerprint, so support can correlate them, but the
    hostname itself is not disclosed. This is deliberately not salted: a per-report salt would
    destroy the correlation that makes the fingerprint useful, and the input space of hostnames is
    small enough that a salt would not make this a privacy control on its own. It is a redaction,
    not an anonymisation, and the docs say so.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class CpuFacts:
    model: str
    cores_physical: int | None
    cores_logical: int | None
    architecture: str


@dataclass(frozen=True)
class MemoryFacts:
    total_gb: float
    available_gb: float
    percent_used: float


@dataclass(frozen=True)
class DiskFacts:
    mountpoint: str
    filesystem: str
    total_gb: float
    free_gb: float
    percent_used: float


@dataclass(frozen=True)
class OsFacts:
    """Operating-system identity.

    ``build`` and ``display_version`` drive applicability: a tweak that is documented for build
    22621 must not be offered on 19045, and the planner needs to be able to say so rather than
    guessing from a marketing name.
    """

    system: str
    release: str
    edition: str | None = None
    display_version: str | None = None
    build: str | None = None
    product_name: str | None = None
    registered_owner: str | None = None  # identifier: redacted by default


@dataclass(frozen=True)
class SystemFacts:
    """Everything inspection collected, plus what it could not collect and why."""

    collected_at: datetime
    os: OsFacts
    is_admin: bool
    python_version: str
    hostname: str | None = None  # identifier: redacted by default
    machine_fingerprint: str = ""
    cpu: CpuFacts | None = None
    memory: MemoryFacts | None = None
    disks: tuple[DiskFacts, ...] = ()
    boot_time: datetime | None = None
    uptime_hours: float | None = None
    collection_notes: tuple[str, ...] = field(default=())

    @property
    def is_windows(self) -> bool:
        return self.os.system == "Windows"

    def to_dict(self, *, include_identifiers: bool = False) -> dict[str, Any]:
        """Serialise for ``--json``.

        Args:
            include_identifiers: Include hostname and registered owner. Off by default: reports get
                pasted into issue trackers and chat.
        """
        data: dict[str, Any] = {
            "collected_at": self.collected_at.isoformat(),
            "machine_fingerprint": self.machine_fingerprint,
            "is_admin": self.is_admin,
            "python_version": self.python_version,
            "os": {k: v for k, v in asdict(self.os).items() if k != "registered_owner"},
            "cpu": asdict(self.cpu) if self.cpu else None,
            "memory": asdict(self.memory) if self.memory else None,
            "disks": [asdict(d) for d in self.disks],
            "boot_time": self.boot_time.isoformat() if self.boot_time else None,
            "uptime_hours": self.uptime_hours,
            "collection_notes": list(self.collection_notes),
            "identifiers_included": include_identifiers,
        }
        if include_identifiers:
            data["hostname"] = self.hostname
            data["os"]["registered_owner"] = self.os.registered_owner
        return data


def _check_admin() -> bool:
    """Whether the current process is elevated.

    On Windows this answers "is this token elevated", which is not the same question as "may this
    process write HKLM" -- that depends on the key's ACL. The planner treats it as a necessary but
    not sufficient condition and still verifies each write by reading it back (defect BASE-011).
    """
    if platform.system() == "Windows":
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:  # pragma: no cover - platforms without geteuid
        return False


def _windows_os_facts(notes: list[str]) -> OsFacts:
    base = OsFacts(system=platform.system(), release=platform.release())
    if not HAS_WINREG:  # pragma: no cover - only reachable on a broken Windows install
        notes.append("winreg unavailable: OS edition and build could not be read")
        return base

    try:  # pragma: no cover - Windows only
        with winreg.OpenKey(  # type: ignore[attr-defined]
            winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            0,
            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),  # type: ignore[attr-defined]
        ) as key:

            def read(name: str) -> str | None:
                try:
                    return str(winreg.QueryValueEx(key, name)[0])  # type: ignore[attr-defined]
                except OSError:
                    return None

            build = read("CurrentBuildNumber") or read("CurrentBuild")
            ubr = read("UBR")
            return OsFacts(
                system=base.system,
                release=base.release,
                edition=read("EditionID"),
                display_version=read("DisplayVersion") or read("ReleaseId"),
                build=f"{build}.{ubr}" if build and ubr else build,
                product_name=read("ProductName"),
                registered_owner=read("RegisteredOwner"),
            )
    except OSError as exc:  # pragma: no cover - Windows only
        notes.append(f"could not read Windows version key: {exc}")
        return base


def gather() -> SystemFacts:
    """Collect machine facts. Read-only, unprivileged, and safe on any platform."""
    notes: list[str] = []
    hostname = socket.gethostname()

    if platform.system() == "Windows":
        os_facts = _windows_os_facts(notes)
    else:
        os_facts = OsFacts(system=platform.system(), release=platform.release())
        notes.append(
            f"running on {platform.system()}: Windows-specific facts were not collected"
        )

    cpu: CpuFacts | None = None
    memory: MemoryFacts | None = None
    disks: list[DiskFacts] = []
    boot_time: datetime | None = None
    uptime_hours: float | None = None

    if not HAS_PSUTIL:
        notes.append("psutil is not installed: CPU, memory, disk and uptime facts are unavailable")
    else:
        cpu = CpuFacts(
            model=platform.processor() or "unknown",
            cores_physical=psutil.cpu_count(logical=False),
            cores_logical=psutil.cpu_count(logical=True),
            architecture=platform.machine(),
        )
        mem = psutil.virtual_memory()
        memory = MemoryFacts(
            total_gb=round(mem.total / 1024**3, 2),
            available_gb=round(mem.available / 1024**3, 2),
            percent_used=round(mem.percent, 1),
        )
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (PermissionError, OSError):
                # An unreadable mount is reported, not silently dropped: a cleanup plan that
                # cannot see a volume must not imply it inspected it.
                notes.append(f"could not read usage for {partition.mountpoint}")
                continue
            disks.append(
                DiskFacts(
                    mountpoint=partition.mountpoint,
                    filesystem=partition.fstype,
                    total_gb=round(usage.total / 1024**3, 2),
                    free_gb=round(usage.free / 1024**3, 2),
                    percent_used=round(usage.percent, 1),
                )
            )
        boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
        uptime_hours = round((_utcnow() - boot_time).total_seconds() / 3600, 1)

    return SystemFacts(
        collected_at=_utcnow(),
        os=os_facts,
        is_admin=_check_admin(),
        python_version=platform.python_version(),
        hostname=hostname,
        machine_fingerprint=fingerprint(hostname),
        cpu=cpu,
        memory=memory,
        disks=tuple(disks),
        boot_time=boot_time,
        uptime_hours=uptime_hours,
        collection_notes=tuple(notes),
    )


def python_supported() -> bool:
    return sys.version_info >= (3, 10)
