"""Deterministic in-memory backends with fault injection.

These are the machine the test suite runs against. They are deliberately strict -- stricter than
Windows in places -- because a fake that is more permissive than the real thing lets bugs through:

- Registry value types are enforced. Writing an ``int`` as ``REG_SZ`` raises rather than coercing.
- Service names compare case-insensitively, as they do on Windows (defect SVC-001).
- Disabling a service that a running service depends on is refused (defect SVC-002).
- Every write is read back internally, so a fake that silently dropped a write would fail its own
  contract tests.

Fault injection is by (method, target) so a test can say "the third registry write fails with
permission_denied" and get exactly that, deterministically, with no timing dependence.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..domain.enums import Presence, RegistryView
from ..domain.state import (
    FileState,
    PowerSchemeState,
    RegistryValueState,
    ScheduledTaskState,
    ServiceState,
)
from .protocols import BackendError, Backends


@dataclass
class Fault:
    """One injected failure."""

    #: Method name, e.g. "write_value".
    method: str
    #: Substring matched against the target identifier, or None to match any target.
    target: str | None = None
    category: str = "permission_denied"
    message: str = "injected fault"
    #: How many matching calls to fail. None means every one.
    times: int | None = 1
    #: Fail *after* performing the mutation, simulating a crash between write and journal update.
    after_effect: bool = False
    _fired: int = field(default=0, init=False)

    def matches(self, method: str, target: str) -> bool:
        if self.method != method:
            return False
        if self.target is not None and self.target.casefold() not in target.casefold():
            return False
        return self.times is None or self._fired < self.times

    def fire(self) -> BackendError:
        self._fired += 1
        return BackendError(f"{self.message} ({self.method} on {self.target or 'any'})",
                            category=self.category)


class FaultInjector:
    """Shared fault registry. One per fake machine."""

    def __init__(self) -> None:
        self._faults: list[Fault] = []
        #: Every call, in order, for assertions about call sequences.
        self.calls: list[tuple[str, str]] = []

    def add(self, fault: Fault) -> Fault:
        self._faults.append(fault)
        return fault

    def fail(self, method: str, target: str | None = None, **kwargs: Any) -> Fault:
        return self.add(Fault(method=method, target=target, **kwargs))

    def check(self, method: str, target: str, *, phase: str = "before") -> None:
        """Raise if a fault is registered for this call. ``phase`` selects pre/post-effect faults."""
        if phase == "before":
            self.calls.append((method, target))
        for fault in self._faults:
            if fault.after_effect != (phase == "after"):
                continue
            if fault.matches(method, target):
                raise fault.fire()

    def clear(self) -> None:
        self._faults.clear()
        self.calls.clear()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: Value types the fake understands, and the Python types they accept. Enforced, because a real
#: REG_DWORD will not hold a string and a fake that accepts one hides the bug until Windows.
_REGISTRY_TYPES: dict[str, tuple[type, ...]] = {
    "REG_SZ": (str,),
    "REG_EXPAND_SZ": (str,),
    "REG_MULTI_SZ": (tuple, list),
    "REG_DWORD": (int,),
    "REG_QWORD": (int,),
    "REG_BINARY": (bytes,),
}


class FakeRegistryBackend:
    """In-memory registry keyed by (view, target_sid, hive, subkey, value_name)."""

    def __init__(self, faults: FaultInjector | None = None) -> None:
        self.faults = faults or FaultInjector()
        self._values: dict[tuple[str, str, str, str, str], tuple[str, Any]] = {}
        self._keys: set[tuple[str, str, str, str]] = set()

    # -- test helpers ------------------------------------------------------

    def seed(
        self,
        hive: str,
        subkey: str,
        value_name: str,
        value_type: str,
        data: Any,
        *,
        view: RegistryView = RegistryView.NATIVE,
        target_sid: str | None = None,
    ) -> None:
        """Place a value directly, bypassing guards and faults. Test setup only."""
        self._validate_type(value_type, data)
        key = self._key(view, target_sid, hive, subkey)
        self._keys.add(key)
        self._values[(*key, value_name)] = (value_type, data)

    def seed_key(self, hive: str, subkey: str, *, view: RegistryView = RegistryView.NATIVE,
                 target_sid: str | None = None) -> None:
        self._keys.add(self._key(view, target_sid, hive, subkey))

    def snapshot(self) -> dict[str, tuple[str, Any]]:
        """Everything currently stored, for whole-machine equality assertions after rollback."""
        return {"|".join(k): v for k, v in sorted(self._values.items())}

    # -- backend interface -------------------------------------------------

    def read_value(
        self,
        hive: str,
        subkey: str,
        value_name: str,
        *,
        view: RegistryView = RegistryView.NATIVE,
        target_sid: str | None = None,
    ) -> RegistryValueState:
        target = f"{hive}\\{subkey}\\{value_name}"
        self.faults.check("read_value", target)

        key = self._key(view, target_sid, hive, subkey)
        if key not in self._keys:
            presence, value_type, data = Presence.CONTAINER_ABSENT, None, None
        elif (*key, value_name) not in self._values:
            presence, value_type, data = Presence.ABSENT, None, None
        else:
            value_type, data = self._values[(*key, value_name)]
            presence = Presence.PRESENT

        return RegistryValueState(
            hive=hive,
            subkey=subkey,
            value_name=value_name,
            presence=presence,
            view=view,
            value_type=value_type,
            data=data,
            target_sid=target_sid,
        )

    def write_value(self, state: RegistryValueState) -> None:
        target = state.path
        self.faults.check("write_value", target)

        key = self._key(state.view, state.target_sid, state.hive, state.subkey)

        if state.presence is Presence.PRESENT:
            self._validate_type(state.value_type or "", state.data)
            self._keys.add(key)
            self._values[(*key, state.value_name)] = (state.value_type or "", state.data)
        elif state.presence is Presence.ABSENT:
            self._values.pop((*key, state.value_name), None)
            self._keys.add(key)
        else:  # CONTAINER_ABSENT: restore the key itself to not existing
            for stored in [k for k in self._values if k[:4] == key]:
                self._values.pop(stored)
            self._keys.discard(key)

        self.faults.check("write_value", target, phase="after")

        # Read-back verification (REG-003): the fake holds itself to the same contract the Windows
        # backend must meet, so an operation that relies on it is testing the real invariant.
        written = self.read_value(
            state.hive, state.subkey, state.value_name,
            view=state.view, target_sid=state.target_sid,
        )
        if not written.equals(state):
            raise BackendError(
                f"read-back verification failed for {target}", category="io_error"
            )

    def key_exists(self, hive: str, subkey: str, *, view: RegistryView = RegistryView.NATIVE) -> bool:
        return any(k[0] == view.value and k[2] == hive and k[3] == subkey for k in self._keys)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _key(
        view: RegistryView, target_sid: str | None, hive: str, subkey: str
    ) -> tuple[str, str, str, str]:
        return (view.value, target_sid or "", hive, subkey)

    @staticmethod
    def _validate_type(value_type: str, data: Any) -> None:
        expected = _REGISTRY_TYPES.get(value_type)
        if expected is None:
            raise BackendError(
                f"unknown registry value type {value_type!r}. Defaulting an unknown type to string "
                "silently corrupts binary data (defect REG-005).",
                category="unsupported",
            )
        if not isinstance(data, expected):
            raise BackendError(
                f"{value_type} cannot hold {type(data).__name__}", category="io_error"
            )
        if value_type == "REG_DWORD" and not 0 <= int(data) <= 0xFFFFFFFF:  # type: ignore[call-overload]
            raise BackendError("REG_DWORD out of range", category="io_error")


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

class FakeServiceBackend:
    """In-memory service database with dependency enforcement."""

    def __init__(self, faults: FaultInjector | None = None) -> None:
        self.faults = faults or FaultInjector()
        self._services: dict[str, ServiceState] = {}

    def seed(self, state: ServiceState) -> None:
        self._services[state.key] = state

    def snapshot(self) -> dict[str, Any]:
        return {k: v.to_payload() for k, v in sorted(self._services.items())}

    def read_service(self, name: str) -> ServiceState:
        self.faults.check("read_service", name)
        existing = self._services.get(name.casefold())
        if existing is None:
            return ServiceState(name=name, presence=Presence.ABSENT)
        return existing

    def write_service(self, state: ServiceState) -> None:
        self.faults.check("write_service", state.name)

        current = self._services.get(state.key)
        if current is None or current.presence is not Presence.PRESENT:
            raise BackendError(f"service {state.name} does not exist", category="not_found")

        # SVC-002: refuse to break a running dependent rather than discovering it at reboot.
        if state.start_type == "disabled" or state.running is False:
            blocking = [
                other.name
                for other in self._services.values()
                if other.presence is Presence.PRESENT
                and other.running
                and state.key in {d.casefold() for d in other.dependencies}
            ]
            if blocking:
                raise BackendError(
                    f"{state.name} is required by running service(s): {', '.join(sorted(blocking))}",
                    category="busy",
                )

        # SVC-003: a failed stop must not be followed by a disable. Modelled by applying the run
        # state first and refusing to continue if it did not take.
        updated = ServiceState(
            name=current.name,
            presence=Presence.PRESENT,
            start_type=state.start_type if state.start_type is not None else current.start_type,
            running=state.running if state.running is not None else current.running,
            display_name=current.display_name,
            dependencies=current.dependencies,
            dependents=current.dependents,
        )
        self._services[current.key] = updated

        self.faults.check("write_service", state.name, phase="after")

        read_back = self.read_service(current.name)
        if read_back.start_type != updated.start_type or read_back.running != updated.running:
            raise BackendError(f"read-back verification failed for {state.name}", category="io_error")


# ---------------------------------------------------------------------------
# Files, power, tasks, identity
# ---------------------------------------------------------------------------

class FakeFileBackend:
    """In-memory filesystem holding content by path, with an archive store."""

    def __init__(self, faults: FaultInjector | None = None) -> None:
        self.faults = faults or FaultInjector()
        self._files: dict[str, bytes] = {}
        self._archive: dict[str, bytes] = {}

    def seed(self, path: str, content: bytes) -> None:
        self._files[path] = content

    def snapshot(self) -> dict[str, str]:
        return {p: hashlib.sha256(c).hexdigest() for p, c in sorted(self._files.items())}

    def read_file_state(self, path: str) -> FileState:
        self.faults.check("read_file_state", path)
        content = self._files.get(path)
        if content is None:
            return FileState(path=path, presence=Presence.ABSENT)
        return FileState(
            path=path,
            presence=Presence.PRESENT,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )

    def archive(self, path: str) -> str:
        self.faults.check("archive", path)
        content = self._files.get(path)
        if content is None:
            raise BackendError(f"cannot archive missing file {path}", category="not_found")
        ref = hashlib.sha256(content).hexdigest()
        self._archive[ref] = content
        return ref

    def restore(self, state: FileState) -> None:
        self.faults.check("restore", state.path)
        if state.presence is Presence.ABSENT:
            self._files.pop(state.path, None)
            return
        if state.content_ref is None:
            raise BackendError(
                f"cannot restore {state.path}: no archived content was captured",
                category="not_found",
            )
        content = self._archive.get(state.content_ref)
        if content is None:
            raise BackendError(f"archived content {state.content_ref} is missing", category="io_error")
        self._files[state.path] = content

    def write(self, path: str, content: bytes) -> None:
        """Direct write, used by tests to simulate a user editing a file after an apply."""
        self._files[path] = content


class FakePowerBackend:
    def __init__(self, faults: FaultInjector | None = None, active: str = "381b4222-guid-balanced") -> None:
        self.faults = faults or FaultInjector()
        self._active = active

    def read_active_scheme(self) -> PowerSchemeState:
        self.faults.check("read_active_scheme", self._active)
        return PowerSchemeState(active_guid=self._active)

    def write_active_scheme(self, state: PowerSchemeState) -> None:
        self.faults.check("write_active_scheme", state.active_guid)
        self._active = state.active_guid
        self.faults.check("write_active_scheme", state.active_guid, phase="after")


class FakeScheduledTaskBackend:
    def __init__(self, faults: FaultInjector | None = None) -> None:
        self.faults = faults or FaultInjector()
        self._tasks: dict[str, ScheduledTaskState] = {}

    def seed(self, state: ScheduledTaskState) -> None:
        self._tasks[state.task_path] = state

    def read_task(self, task_path: str) -> ScheduledTaskState:
        self.faults.check("read_task", task_path)
        return self._tasks.get(task_path) or ScheduledTaskState(
            task_path=task_path, presence=Presence.ABSENT
        )

    def write_task(self, state: ScheduledTaskState) -> None:
        self.faults.check("write_task", state.task_path)
        if state.task_path not in self._tasks:
            raise BackendError(f"task {state.task_path} does not exist", category="not_found")
        self._tasks[state.task_path] = state
        self.faults.check("write_task", state.task_path, phase="after")


class FakeIdentityBackend:
    def __init__(self, sid: str | None = "S-1-5-21-fake-1001") -> None:
        self._sid = sid

    def interactive_user_sid(self) -> str | None:
        return self._sid


@dataclass
class FakeMachine:
    """A whole fake machine: all backends sharing one fault injector.

    :meth:`snapshot` is the basis of the exact-rollback proof -- take one before apply, one after
    rollback, and assert they are identical. Whole-machine equality catches collateral damage that
    per-operation state comparison would miss.
    """

    faults: FaultInjector = field(default_factory=FaultInjector)
    registry: FakeRegistryBackend = field(init=False)
    services: FakeServiceBackend = field(init=False)
    files: FakeFileBackend = field(init=False)
    power: FakePowerBackend = field(init=False)
    tasks: FakeScheduledTaskBackend = field(init=False)
    identity: FakeIdentityBackend = field(default_factory=FakeIdentityBackend)

    def __post_init__(self) -> None:
        self.registry = FakeRegistryBackend(self.faults)
        self.services = FakeServiceBackend(self.faults)
        self.files = FakeFileBackend(self.faults)
        self.power = FakePowerBackend(self.faults)
        self.tasks = FakeScheduledTaskBackend(self.faults)

    def snapshot(self) -> dict[str, Any]:
        return {
            "registry": self.registry.snapshot(),
            "services": self.services.snapshot(),
            "files": self.files.snapshot(),
            "power": self.power.read_active_scheme().active_guid,
            "tasks": {p: t.to_payload() for p, t in sorted(self.tasks._tasks.items())},
        }

    def backends(self) -> Backends:
        return Backends(
            registry=self.registry,
            services=self.services,
            files=self.files,
            power=self.power,
            tasks=self.tasks,
            identity=self.identity,
        )


def fault_free() -> Callable[[], FakeMachine]:
    """Factory for a machine with no injected faults, for readability at call sites."""
    return FakeMachine
