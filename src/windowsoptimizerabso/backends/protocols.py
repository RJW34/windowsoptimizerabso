"""Backend interfaces.

Operations are written against these, never against ``winreg`` or ``sc.exe`` directly. That is what
makes the lifecycle testable: the same operation code runs against a deterministic fake machine in
CI and against Windows on a real one.

Two rules every real implementation must follow:

- **Read back after every write.** A write that returned success and did not take effect is
  indistinguishable from one that worked, unless it is verified (defect REG-003).
- **Distinguish missing from failed.** "This key does not exist" and "I could not read this key"
  lead to different decisions; collapsing them into ``None`` is how the baseline came to treat a
  permission error as an absent value.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.enums import RegistryView
from ..domain.state import (
    FileState,
    PowerSchemeState,
    RegistryValueState,
    ScheduledTaskState,
    ServiceState,
)


class BackendError(Exception):
    """A backend could not complete an operation. Carries a structured category, never a bare bool."""

    def __init__(self, message: str, *, category: str = "unknown") -> None:
        super().__init__(message)
        #: One of: permission_denied, not_found, timeout, busy, unsupported, io_error, unknown.
        self.category = category


@runtime_checkable
class RegistryBackend(Protocol):
    def read_value(
        self,
        hive: str,
        subkey: str,
        value_name: str,
        *,
        view: RegistryView = RegistryView.NATIVE,
        target_sid: str | None = None,
    ) -> RegistryValueState:
        """Read one value. Returns a state with the appropriate ``Presence`` if it is missing."""

    def write_value(self, state: RegistryValueState) -> None:
        """Write the value described by ``state``, creating the key if required.

        ``state`` is the *desired* state, including its exact type. Passing a state with
        ``Presence.ABSENT`` deletes the value; ``Presence.CONTAINER_ABSENT`` deletes the key.
        Expressing deletion as a state, rather than a separate method, is what makes restore and
        apply the same code path.
        """

    def key_exists(self, hive: str, subkey: str, *, view: RegistryView = RegistryView.NATIVE) -> bool:
        ...


@runtime_checkable
class ServiceBackend(Protocol):
    def read_service(self, name: str) -> ServiceState:
        """Read a service's configuration. Name comparison is case-insensitive (defect SVC-001)."""

    def write_service(self, state: ServiceState) -> None:
        """Apply the configuration in ``state``, waiting for any state transition to complete.

        Must refuse to disable a service that running services depend on, and must not proceed to
        disable after a stop has failed (defects SVC-002, SVC-003).
        """


@runtime_checkable
class FileBackend(Protocol):
    def read_file_state(self, path: str) -> FileState:
        ...

    def archive(self, path: str) -> str:
        """Copy a file into the backup store and return a content reference."""

    def restore(self, state: FileState) -> None:
        """Restore a file from its archived content, refusing to clobber a later edit."""


@runtime_checkable
class PowerBackend(Protocol):
    def read_active_scheme(self) -> PowerSchemeState:
        ...

    def write_active_scheme(self, state: PowerSchemeState) -> None:
        ...


@runtime_checkable
class ScheduledTaskBackend(Protocol):
    def read_task(self, task_path: str) -> ScheduledTaskState:
        ...

    def write_task(self, state: ScheduledTaskState) -> None:
        ...


@runtime_checkable
class IdentityBackend(Protocol):
    def interactive_user_sid(self) -> str | None:
        """SID of the logged-on interactive user.

        Not the same as the current process's user when running elevated as a different account,
        which is the whole reason this backend exists (defect CORE-014).
        """


class Backends:
    """The set of backends an executor runs against. Injected, never imported at point of use."""

    def __init__(
        self,
        *,
        registry: RegistryBackend | None = None,
        services: ServiceBackend | None = None,
        files: FileBackend | None = None,
        power: PowerBackend | None = None,
        tasks: ScheduledTaskBackend | None = None,
        identity: IdentityBackend | None = None,
    ) -> None:
        self.registry = registry
        self.services = services
        self.files = files
        self.power = power
        self.tasks = tasks
        self.identity = identity

    def require_registry(self) -> RegistryBackend:
        if self.registry is None:
            raise BackendError("no registry backend is available", category="unsupported")
        return self.registry

    def require_services(self) -> ServiceBackend:
        if self.services is None:
            raise BackendError("no service backend is available", category="unsupported")
        return self.services
