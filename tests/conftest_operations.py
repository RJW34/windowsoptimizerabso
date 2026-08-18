"""Shared test fixtures: a small set of real-shaped operations over the fake machine.

These are not toys standing in for the real thing structurally -- they are ordinary
:class:`OperationSpec` instances using the same capture/apply/verify/restore contract that ported
Windows operations will use. If the lifecycle works for these, it works for those.
"""

from __future__ import annotations

from typing import Any

from windowsoptimizerabso.backends.fake import FakeMachine
from windowsoptimizerabso.domain.enums import (
    ActivationRequirement,
    Presence,
    Risk,
    Scope,
)
from windowsoptimizerabso.domain.operation import (
    Applicability,
    Environment,
    Evidence,
    OperationRegistry,
    OperationSpec,
)
from windowsoptimizerabso.domain.state import RegistryValueState, ServiceState, StateSet

DOCS = "https://learn.microsoft.com/windows/example"
USER_SID = "S-1-5-21-fake-1001"


def make_environment(machine: FakeMachine, **overrides: Any) -> Environment:
    defaults: dict[str, Any] = {
        "os_system": "Windows",
        "os_build": "22631.4317",
        "os_edition": "Professional",
        "is_admin": True,
        "target_user_sid": machine.identity.interactive_user_sid(),
    }
    defaults.update(overrides)
    return Environment(**defaults)


def registry_toggle_operation(
    machine: FakeMachine,
    *,
    operation_id: str = "test.registry_toggle",
    hive: str = "HKLM",
    subkey: str = r"SOFTWARE\Test",
    value_name: str = "Toggle",
    desired: int = 1,
    risk: Risk = Risk.LOW,
    conflict_keys: tuple[str, ...] = (),
    depends_on: tuple[str, ...] = (),
    scope: Scope = Scope.MACHINE,
    target_sid: str | None = None,
) -> OperationSpec:
    """A DWORD flip: the shape of most real registry operations."""

    def capture(env: Environment, params: dict[str, Any]) -> StateSet:
        return StateSet((
            machine.registry.read_value(hive, subkey, value_name, target_sid=target_sid),
        ))

    def apply(env: Environment, params: dict[str, Any], captured: StateSet) -> None:
        machine.registry.write_value(
            RegistryValueState(
                hive=hive, subkey=subkey, value_name=value_name,
                presence=Presence.PRESENT, value_type="REG_DWORD",
                data=params.get("value", desired), target_sid=target_sid,
            )
        )

    def restore(env: Environment, params: dict[str, Any], captured: StateSet) -> None:
        for state in captured.states:
            machine.registry.write_value(state)

    def check(env: Environment, params: dict[str, Any]) -> Applicability:
        current = machine.registry.read_value(hive, subkey, value_name, target_sid=target_sid)
        if current.presence is Presence.PRESENT and current.data == params.get("value", desired):
            return Applicability.satisfied()
        return Applicability.yes()

    return OperationSpec(
        operation_id=operation_id,
        title=f"Set {value_name} to {desired}",
        explanation=f"Writes {hive}\\{subkey}\\{value_name} as REG_DWORD.",
        category="test",
        risk=risk,
        scope=scope,
        evidence=Evidence(
            source=DOCS,
            accessed="2026-08-18",
            summary="Documented setting used as a lifecycle fixture.",
            tradeoffs="none known" if risk < Risk.HIGH else "stated tradeoff",
        ),
        capture=capture,
        apply=apply,
        restore=restore,
        check_applicability=check,
        conflict_keys=conflict_keys,
        depends_on=depends_on,
        parameters={"value": lambda v: isinstance(v, int) and 0 <= v <= 0xFFFFFFFF},
    )


def binary_registry_operation(machine: FakeMachine, *, target_sid: str = USER_SID) -> OperationSpec:
    """A REG_BINARY write in a user hive: the case that could not be journalled at all."""
    hive, subkey, value_name = "HKCU", r"Control Panel\Desktop", "UserPreferencesMask"
    new_mask = b"\x90\x12\x03\x80\x10\x00\x00\x00"

    def capture(env: Environment, params: dict[str, Any]) -> StateSet:
        return StateSet((machine.registry.read_value(
            hive, subkey, value_name, target_sid=env.target_user_sid or target_sid),))

    def apply(env: Environment, params: dict[str, Any], captured: StateSet) -> None:
        machine.registry.write_value(RegistryValueState(
            hive=hive, subkey=subkey, value_name=value_name, presence=Presence.PRESENT,
            value_type="REG_BINARY", data=new_mask,
            target_sid=env.target_user_sid or target_sid,
        ))

    def restore(env: Environment, params: dict[str, Any], captured: StateSet) -> None:
        for state in captured.states:
            machine.registry.write_value(state)

    def check(env: Environment, params: dict[str, Any]) -> Applicability:
        return Applicability.yes()

    return OperationSpec(
        operation_id="test.user_preferences_mask",
        title="Set UserPreferencesMask",
        explanation="Writes a REG_BINARY value in the interactive user's hive.",
        category="test",
        risk=Risk.MODERATE,
        scope=Scope.USER,
        activation=ActivationRequirement.EXPLORER_RESTART,
        evidence=Evidence(source=DOCS, accessed="2026-08-18",
                          summary="Binary user-preference bitmask."),
        capture=capture,
        apply=apply,
        restore=restore,
        check_applicability=check,
    )


def service_operation(machine: FakeMachine, service_name: str = "DiagTrack") -> OperationSpec:
    def capture(env: Environment, params: dict[str, Any]) -> StateSet:
        return StateSet((machine.services.read_service(service_name),))

    def apply(env: Environment, params: dict[str, Any], captured: StateSet) -> None:
        machine.services.write_service(
            ServiceState(name=service_name, presence=Presence.PRESENT,
                         start_type="disabled", running=False)
        )

    def restore(env: Environment, params: dict[str, Any], captured: StateSet) -> None:
        for state in captured.states:
            machine.services.write_service(state)

    def check(env: Environment, params: dict[str, Any]) -> Applicability:
        current = machine.services.read_service(service_name)
        if current.presence is not Presence.PRESENT:
            return Applicability.no(f"{service_name} is not installed on this machine")
        if current.start_type == "disabled":
            return Applicability.satisfied()
        return Applicability.yes()

    return OperationSpec(
        operation_id="test.disable_service",
        title=f"Disable {service_name}",
        explanation=f"Sets {service_name} to disabled and stops it.",
        category="test",
        risk=Risk.HIGH,
        scope=Scope.MACHINE,
        activation=ActivationRequirement.IMMEDIATE,
        evidence=Evidence(
            source=DOCS, accessed="2026-08-18",
            summary="Telemetry collection service.",
            tradeoffs="Feedback and diagnostics features stop reporting.",
        ),
        capture=capture,
        apply=apply,
        restore=restore,
        check_applicability=check,
    )


def seeded_machine() -> FakeMachine:
    """A fake machine with the state the fixture operations expect to find."""
    machine = FakeMachine()
    machine.registry.seed_key("HKLM", r"SOFTWARE\Test")
    machine.registry.seed("HKLM", r"SOFTWARE\Test", "Toggle", "REG_DWORD", 0)
    machine.registry.seed(
        "HKCU", r"Control Panel\Desktop", "UserPreferencesMask", "REG_BINARY",
        b"\x9e\x1e\x07\x80\x12\x00\x00\x00", target_sid=USER_SID,
    )
    machine.services.seed(ServiceState(
        name="DiagTrack", presence=Presence.PRESENT, start_type="auto", running=True,
        display_name="Connected User Experiences and Telemetry",
    ))
    machine.services.seed(ServiceState(
        name="RpcSs", presence=Presence.PRESENT, start_type="auto", running=True,
        display_name="Remote Procedure Call",
    ))
    return machine


def registry_with(*specs: OperationSpec) -> OperationRegistry:
    registry = OperationRegistry()
    for spec in specs:
        registry.register(spec)
    return registry
