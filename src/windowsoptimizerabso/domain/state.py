"""Tagged captured-state types.

The rule these types exist to enforce: a captured state must be enough, on its own, to restore
exactly what was there -- including the case where nothing was there. Every type records *how* it
was missing (:class:`~.enums.Presence`), because deleting a value, setting it empty, and never
having had a key all roll back differently.

States are frozen dataclasses with a JSON round-trip through :mod:`.codecs`, so they can go into
the journal and come back byte-identical. Equality is exact: two states are equal only if their
canonical encodings match.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Optional

from . import codecs
from .enums import Presence, RegistryView


class StateError(ValueError):
    """Raised when a captured state is internally inconsistent."""


@dataclass(frozen=True)
class CapturedState:
    """Base class for everything the executor can capture and restore."""

    #: Discriminator persisted in the journal, so a stored blob decodes to the right type.
    kind: ClassVar[str] = "abstract"

    def to_payload(self) -> dict[str, Any]:  # pragma: no cover - overridden
        raise NotImplementedError

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CapturedState:  # pragma: no cover
        raise NotImplementedError

    # -- serialisation -----------------------------------------------------

    def serialise(self) -> str:
        return codecs.dumps({"kind": self.kind, "codec_version": codecs.CODEC_VERSION,
                             "payload": self.to_payload()})

    @staticmethod
    def deserialise(text: str) -> CapturedState:
        blob = codecs.loads(text)
        if not isinstance(blob, dict) or "kind" not in blob:
            raise codecs.DecodeError("captured state blob has no kind discriminator")
        version = blob.get("codec_version")
        if version != codecs.CODEC_VERSION:
            raise codecs.DecodeError(
                f"captured state was written by codec version {version!r}, this build reads "
                f"{codecs.CODEC_VERSION}. Refusing to guess."
            )
        registry = {c.kind: c for c in (RegistryValueState, ServiceState, FileState, PowerSchemeState,
                                        ScheduledTaskState)}
        state_class = registry.get(blob["kind"])
        if state_class is None:
            raise codecs.DecodeError(f"unknown captured state kind {blob['kind']!r}")
        payload = blob.get("payload")
        if not isinstance(payload, dict):
            raise codecs.DecodeError("captured state payload is not an object")
        return state_class.from_payload(payload)

    @property
    def digest(self) -> str:
        return codecs.digest({"kind": self.kind, "payload": self.to_payload()})

    def equals(self, other: "CapturedState") -> bool:
        """Exact equality, used to prove a rollback restored the captured state."""
        return (
            type(self) is type(other)
            and codecs.states_equal(self.to_payload(), other.to_payload())
        )


@dataclass(frozen=True)
class RegistryValueState(CapturedState):
    """One registry value, captured precisely enough to restore it.

    Records hive, subkey, value name, view, exact type and exact data. The baseline captured the
    *target* type rather than the original one, so restoring a value that had been ``REG_SZ`` wrote
    it back as whatever the tweak used -- typically ``REG_DWORD`` (defect REG-001).
    """

    kind: ClassVar[str] = "registry_value"

    hive: str
    subkey: str
    value_name: str
    presence: Presence
    view: RegistryView = RegistryView.NATIVE
    #: The exact Windows type constant name, e.g. ``REG_BINARY``. Never inferred from the data:
    #: an unknown type defaulting to string silently corrupts binary values (defect REG-005).
    value_type: Optional[str] = None
    data: Any = None
    #: Required when the hive is user-scoped, so an elevated executor writes the interactive
    #: user's hive rather than its own (defects PRV-007, CORE-014).
    target_sid: Optional[str] = None

    def __post_init__(self) -> None:
        if self.presence is Presence.PRESENT:
            if self.value_type is None:
                raise StateError("a present registry value must record its exact type")
        elif self.data is not None or self.value_type is not None:
            raise StateError(f"{self.presence.value} registry value must not carry data or a type")
        if self.hive.upper() in {"HKCU", "HKEY_CURRENT_USER", "HKU", "HKEY_USERS"} and not self.target_sid:
            raise StateError(
                f"user-scoped registry state for {self.hive}\\{self.subkey} must name a target SID; "
                "an elevated process's HKCU is the elevating account, not the interactive user"
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "hive": self.hive,
            "subkey": self.subkey,
            "value_name": self.value_name,
            "presence": self.presence.value,
            "view": self.view.value,
            "value_type": self.value_type,
            "data": self.data,
            "target_sid": self.target_sid,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RegistryValueState:
        return cls(
            hive=payload["hive"],
            subkey=payload["subkey"],
            value_name=payload["value_name"],
            presence=Presence(payload["presence"]),
            view=RegistryView(payload.get("view", RegistryView.NATIVE.value)),
            value_type=payload.get("value_type"),
            data=payload.get("data"),
            target_sid=payload.get("target_sid"),
        )

    @property
    def path(self) -> str:
        return f"{self.hive}\\{self.subkey}\\{self.value_name}"


@dataclass(frozen=True)
class ServiceState(CapturedState):
    """A Windows service's configuration and run state.

    Service names are case-insensitive on Windows, so :attr:`key` is used for identity comparisons.
    The baseline's critical-service protection compared names case-sensitively, meaning
    ``diagtrack`` bypassed a guard written for ``DiagTrack`` (defect SVC-001).
    """

    kind: ClassVar[str] = "service"

    name: str
    presence: Presence
    start_type: Optional[str] = None
    running: Optional[bool] = None
    display_name: Optional[str] = None
    #: Services that must be running for this one to start. Captured so a restore can order
    #: itself correctly rather than failing halfway (defect SVC-002).
    dependencies: tuple[str, ...] = ()
    dependents: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.presence is Presence.PRESENT:
            if self.start_type is None or self.running is None:
                raise StateError("a present service must record both start type and run state")
        elif self.start_type is not None or self.running is not None:
            raise StateError("an absent service must not carry configuration")

    @property
    def key(self) -> str:
        """Case-folded identity, matching Windows' own comparison."""
        return self.name.casefold()

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "presence": self.presence.value,
            "start_type": self.start_type,
            "running": self.running,
            "display_name": self.display_name,
            "dependencies": tuple(self.dependencies),
            "dependents": tuple(self.dependents),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ServiceState:
        return cls(
            name=payload["name"],
            presence=Presence(payload["presence"]),
            start_type=payload.get("start_type"),
            running=payload.get("running"),
            display_name=payload.get("display_name"),
            dependencies=tuple(payload.get("dependencies") or ()),
            dependents=tuple(payload.get("dependents") or ()),
        )


@dataclass(frozen=True)
class FileState(CapturedState):
    """A file's identity and content digest.

    Content is *not* stored inline: a large file belongs in the backup store, referenced by digest.
    What is stored here is enough to detect that the file changed since capture, which is what
    stops a rollback from clobbering an edit the user made after the apply (defect BAK-008).
    """

    kind: ClassVar[str] = "file"

    path: str
    presence: Presence
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    modified_at: Optional[datetime] = None
    #: Where the captured content lives in the backup store, if it was archived.
    content_ref: Optional[str] = None

    def __post_init__(self) -> None:
        if self.presence is Presence.PRESENT and self.sha256 is None:
            raise StateError("a present file must record a content digest")
        if self.presence is not Presence.PRESENT and self.sha256 is not None:
            raise StateError("an absent file must not record a content digest")

    def to_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "presence": self.presence.value,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "content_ref": self.content_ref,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> FileState:
        return cls(
            path=payload["path"],
            presence=Presence(payload["presence"]),
            sha256=payload.get("sha256"),
            size_bytes=payload.get("size_bytes"),
            modified_at=payload.get("modified_at"),
            content_ref=payload.get("content_ref"),
        )


@dataclass(frozen=True)
class PowerSchemeState(CapturedState):
    """The active power scheme.

    Captured as the exact prior GUID. The baseline's power operation duplicated the Ultimate
    Performance scheme and activated it without recording what had been active, so there was
    nothing to go back to (defect GAM-005).
    """

    kind: ClassVar[str] = "power_scheme"

    active_guid: str
    display_name: Optional[str] = None

    def to_payload(self) -> dict[str, Any]:
        return {"active_guid": self.active_guid, "display_name": self.display_name}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> PowerSchemeState:
        return cls(active_guid=payload["active_guid"], display_name=payload.get("display_name"))


@dataclass(frozen=True)
class ScheduledTaskState(CapturedState):
    """A scheduled task's enabled state and full definition.

    The XML is captured because re-enabling a task is not the inverse of disabling one if anything
    else about the definition changed; restoring the definition is (defect BAK-004).
    """

    kind: ClassVar[str] = "scheduled_task"

    task_path: str
    presence: Presence
    enabled: Optional[bool] = None
    definition_xml: Optional[str] = None

    def __post_init__(self) -> None:
        if self.presence is Presence.PRESENT and self.enabled is None:
            raise StateError("a present scheduled task must record its enabled state")

    def to_payload(self) -> dict[str, Any]:
        return {
            "task_path": self.task_path,
            "presence": self.presence.value,
            "enabled": self.enabled,
            "definition_xml": self.definition_xml,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ScheduledTaskState:
        return cls(
            task_path=payload["task_path"],
            presence=Presence(payload["presence"]),
            enabled=payload.get("enabled"),
            definition_xml=payload.get("definition_xml"),
        )


@dataclass(frozen=True)
class StateSet:
    """An ordered collection of captured states, as taken for one operation.

    An operation usually touches more than one thing, and rollback has to restore all of them or
    report exactly which it could not. A set-level digest lets drift detection ask one question
    instead of N.
    """

    states: tuple[CapturedState, ...] = field(default_factory=tuple)

    @property
    def digest(self) -> str:
        return codecs.digest([s.digest for s in self.states])

    def serialise(self) -> str:
        return codecs.dumps([codecs.loads(s.serialise()) for s in self.states])

    @staticmethod
    def deserialise(text: str) -> StateSet:
        blobs = codecs.loads(text)
        if not isinstance(blobs, list):
            raise codecs.DecodeError("state set is not an array")
        return StateSet(tuple(CapturedState.deserialise(codecs.dumps(b)) for b in blobs))

    def equals(self, other: "StateSet") -> bool:
        return len(self.states) == len(other.states) and all(
            a.equals(b) for a, b in zip(self.states, other.states)
        )

    def differences(self, other: "StateSet") -> tuple[str, ...]:
        """Human-readable description of what does not match, for residual-drift reporting."""
        if len(self.states) != len(other.states):
            return (f"expected {len(self.states)} captured states, found {len(other.states)}",)
        return tuple(
            f"{describe(a)} differs from the captured state"
            for a, b in zip(self.states, other.states)
            if not a.equals(b)
        )


def describe(state: CapturedState) -> str:
    """Short identifier for a state, for logs and drift reports. Never includes value data."""
    if isinstance(state, RegistryValueState):
        return f"registry {state.path} [{state.view.value}]"
    if isinstance(state, ServiceState):
        return f"service {state.name}"
    if isinstance(state, FileState):
        return f"file {state.path}"
    if isinstance(state, PowerSchemeState):
        return "active power scheme"
    if isinstance(state, ScheduledTaskState):
        return f"scheduled task {state.task_path}"
    return state.kind
