"""Contract tests for the fake machine (gate G3 prerequisite, defect TST-001).

The fakes are the machine the whole suite runs against, so they get tested like production code. A
fake that is more permissive than Windows would let bugs through to a real system: these assert
the specific strictnesses that matter -- registry type enforcement, case-insensitive service
identity, dependency refusal, and read-back verification.
"""

from __future__ import annotations

import pytest
from conftest_operations import USER_SID, seeded_machine

from windowsoptimizerabso.backends.fake import FakeMachine, FaultInjector
from windowsoptimizerabso.backends.protocols import (
    BackendError,
    RegistryBackend,
    ServiceBackend,
)
from windowsoptimizerabso.domain.enums import Presence, RegistryView
from windowsoptimizerabso.domain.state import RegistryValueState, ServiceState


def test_fakes_satisfy_the_declared_protocols():
    machine = FakeMachine()
    assert isinstance(machine.registry, RegistryBackend)
    assert isinstance(machine.services, ServiceBackend)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_reading_a_missing_value_distinguishes_missing_key_from_missing_value():
    machine = FakeMachine()
    machine.registry.seed_key("HKLM", r"SOFTWARE\Present")

    no_key = machine.registry.read_value("HKLM", r"SOFTWARE\Absent", "V")
    no_value = machine.registry.read_value("HKLM", r"SOFTWARE\Present", "V")

    assert no_key.presence is Presence.CONTAINER_ABSENT
    assert no_value.presence is Presence.ABSENT


def test_write_then_read_returns_the_exact_value():
    machine = FakeMachine()
    state = RegistryValueState(
        hive="HKLM", subkey=r"SOFTWARE\Test", value_name="Binary",
        presence=Presence.PRESENT, value_type="REG_BINARY", data=b"\x00\xff",
    )
    machine.registry.write_value(state)
    assert machine.registry.read_value("HKLM", r"SOFTWARE\Test", "Binary").equals(state)


def test_writing_an_absent_state_deletes_the_value():
    """Deletion is expressed as a state, so apply and restore are the same code path."""
    machine = seeded_machine()
    machine.registry.write_value(
        RegistryValueState(hive="HKLM", subkey=r"SOFTWARE\Test", value_name="Toggle",
                           presence=Presence.ABSENT)
    )
    assert machine.registry.read_value("HKLM", r"SOFTWARE\Test", "Toggle").presence is Presence.ABSENT


def test_writing_container_absent_removes_the_key_and_its_values():
    machine = seeded_machine()
    machine.registry.write_value(
        RegistryValueState(hive="HKLM", subkey=r"SOFTWARE\Test", value_name="Toggle",
                           presence=Presence.CONTAINER_ABSENT)
    )
    read = machine.registry.read_value("HKLM", r"SOFTWARE\Test", "Toggle")
    assert read.presence is Presence.CONTAINER_ABSENT
    assert not machine.registry.key_exists("HKLM", r"SOFTWARE\Test")


def test_registry_types_are_enforced_not_coerced():
    """REG-005: a fake that coerces hides the bug until it reaches Windows."""
    machine = FakeMachine()
    with pytest.raises(BackendError) as excinfo:
        machine.registry.write_value(RegistryValueState(
            hive="HKLM", subkey="S", value_name="V", presence=Presence.PRESENT,
            value_type="REG_DWORD", data="not a number",
        ))
    assert excinfo.value.category == "io_error"


def test_an_unknown_registry_type_is_refused_rather_than_defaulted_to_string():
    machine = FakeMachine()
    with pytest.raises(BackendError) as excinfo:
        machine.registry.write_value(RegistryValueState(
            hive="HKLM", subkey="S", value_name="V", presence=Presence.PRESENT,
            value_type="REG_INVENTED", data="x",
        ))
    assert excinfo.value.category == "unsupported"


def test_dword_range_is_enforced():
    machine = FakeMachine()
    with pytest.raises(BackendError):
        machine.registry.write_value(RegistryValueState(
            hive="HKLM", subkey="S", value_name="V", presence=Presence.PRESENT,
            value_type="REG_DWORD", data=0x1_0000_0000,
        ))


def test_views_are_separate_stores():
    """REG-002: WOW6432Node redirection means the same path is two different keys."""
    machine = FakeMachine()
    for view in (RegistryView.NATIVE, RegistryView.WOW64_32):
        machine.registry.write_value(RegistryValueState(
            hive="HKLM", subkey=r"SOFTWARE\App", value_name="V", presence=Presence.PRESENT,
            value_type="REG_DWORD", data=1 if view is RegistryView.NATIVE else 2, view=view,
        ))
    assert machine.registry.read_value("HKLM", r"SOFTWARE\App", "V",
                                       view=RegistryView.NATIVE).data == 1
    assert machine.registry.read_value("HKLM", r"SOFTWARE\App", "V",
                                       view=RegistryView.WOW64_32).data == 2


def test_user_hives_are_separated_by_sid():
    """PRV-007: writing the elevated account's hive instead of the interactive user's."""
    machine = FakeMachine()
    for sid, data in [("S-1-5-21-user", 1), ("S-1-5-21-admin", 2)]:
        machine.registry.write_value(RegistryValueState(
            hive="HKCU", subkey=r"Control Panel\Desktop", value_name="X",
            presence=Presence.PRESENT, value_type="REG_DWORD", data=data, target_sid=sid,
        ))
    assert machine.registry.read_value("HKCU", r"Control Panel\Desktop", "X",
                                       target_sid="S-1-5-21-user").data == 1
    assert machine.registry.read_value("HKCU", r"Control Panel\Desktop", "X",
                                       target_sid="S-1-5-21-admin").data == 2


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

def test_service_lookup_is_case_insensitive():
    """SVC-001: Windows compares service names case-insensitively; the baseline did not."""
    machine = seeded_machine()
    assert machine.services.read_service("diagtrack").presence is Presence.PRESENT
    assert machine.services.read_service("DIAGTRACK").presence is Presence.PRESENT


def test_a_missing_service_reads_as_absent_not_as_an_error():
    machine = seeded_machine()
    assert machine.services.read_service("NoSuchService").presence is Presence.ABSENT


def test_disabling_a_service_a_running_service_depends_on_is_refused():
    """SVC-002: the baseline queried dependents and then ignored them."""
    machine = seeded_machine()
    machine.services.seed(ServiceState(
        name="Dependent", presence=Presence.PRESENT, start_type="auto", running=True,
        dependencies=("DiagTrack",),
    ))
    with pytest.raises(BackendError) as excinfo:
        machine.services.write_service(ServiceState(
            name="DiagTrack", presence=Presence.PRESENT, start_type="disabled", running=False,
        ))
    assert excinfo.value.category == "busy"
    assert "Dependent" in str(excinfo.value)


def test_writing_a_missing_service_is_not_found_not_a_silent_success():
    machine = seeded_machine()
    with pytest.raises(BackendError) as excinfo:
        machine.services.write_service(ServiceState(
            name="Ghost", presence=Presence.PRESENT, start_type="disabled", running=False,
        ))
    assert excinfo.value.category == "not_found"


def test_service_write_preserves_unmodified_fields():
    """SVC-005: restoring must not guess Manual for fields it was not asked to change."""
    machine = seeded_machine()
    machine.services.write_service(ServiceState(
        name="DiagTrack", presence=Presence.PRESENT, start_type="disabled", running=False,
    ))
    after = machine.services.read_service("DiagTrack")
    assert after.display_name == "Connected User Experiences and Telemetry"


# ---------------------------------------------------------------------------
# Fault injection (TST-001, TST-003)
# ---------------------------------------------------------------------------

def test_a_fault_fires_the_requested_number_of_times():
    machine = FakeMachine()
    machine.registry.seed_key("HKLM", "S")
    machine.faults.fail("read_value", "V", times=2, category="permission_denied")

    for _ in range(2):
        with pytest.raises(BackendError):
            machine.registry.read_value("HKLM", "S", "V")
    machine.registry.read_value("HKLM", "S", "V")  # third call succeeds


def test_a_fault_can_be_targeted_at_one_value():
    machine = FakeMachine()
    machine.registry.seed_key("HKLM", "S")
    machine.faults.fail("read_value", "Targeted", times=None)

    with pytest.raises(BackendError):
        machine.registry.read_value("HKLM", "S", "Targeted")
    machine.registry.read_value("HKLM", "S", "Other")


def test_an_after_effect_fault_leaves_the_mutation_in_place():
    """The crash-after-write case: the machine changed but nothing recorded it."""
    machine = FakeMachine()
    machine.faults.fail("write_value", "Toggle", after_effect=True)

    with pytest.raises(BackendError):
        machine.registry.write_value(RegistryValueState(
            hive="HKLM", subkey="S", value_name="Toggle", presence=Presence.PRESENT,
            value_type="REG_DWORD", data=1,
        ))
    assert machine.registry.read_value("HKLM", "S", "Toggle").data == 1


def test_calls_are_recorded_in_order():
    machine = FakeMachine()
    machine.registry.seed_key("HKLM", "S")
    machine.registry.read_value("HKLM", "S", "A")
    machine.registry.read_value("HKLM", "S", "B")
    assert [c[0] for c in machine.faults.calls] == ["read_value", "read_value"]
    assert "A" in machine.faults.calls[0][1]


def test_backends_share_one_injector():
    machine = FakeMachine()
    assert machine.registry.faults is machine.services.faults is machine.faults


def test_injector_can_be_cleared_between_phases():
    injector = FaultInjector()
    injector.fail("read_value")
    injector.clear()
    injector.check("read_value", "anything")  # no raise


# ---------------------------------------------------------------------------
# Whole-machine snapshots
# ---------------------------------------------------------------------------

def test_snapshot_captures_every_subsystem():
    machine = seeded_machine()
    snapshot = machine.snapshot()
    assert set(snapshot) == {"registry", "services", "files", "power", "tasks"}
    assert any("Toggle" in key for key in snapshot["registry"])


def test_snapshots_are_equal_only_when_the_machine_is_unchanged():
    machine = seeded_machine()
    before = machine.snapshot()
    machine.registry.write_value(RegistryValueState(
        hive="HKLM", subkey=r"SOFTWARE\Test", value_name="Toggle", presence=Presence.PRESENT,
        value_type="REG_DWORD", data=1,
    ))
    assert machine.snapshot() != before

    machine.registry.write_value(RegistryValueState(
        hive="HKLM", subkey=r"SOFTWARE\Test", value_name="Toggle", presence=Presence.PRESENT,
        value_type="REG_DWORD", data=0,
    ))
    assert machine.snapshot() == before


def test_snapshot_distinguishes_a_user_hive_write():
    machine = seeded_machine()
    before = machine.snapshot()
    machine.registry.write_value(RegistryValueState(
        hive="HKCU", subkey=r"Control Panel\Desktop", value_name="UserPreferencesMask",
        presence=Presence.PRESENT, value_type="REG_BINARY", data=b"\x01" * 8,
        target_sid=USER_SID,
    ))
    assert machine.snapshot() != before
