"""Domain model invariants (gate G2).

Evidence for CORE-007 (binary registry state could not be serialised at all), CORE-010, CORE-016,
CORE-017, REG-001, REG-002, REG-005, PRV-007, BAK-005 and SVC-001.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from windowsoptimizerabso.domain import codecs
from windowsoptimizerabso.domain.enums import (
    LifecyclePhase,
    OperationStatus,
    Presence,
    RegistryView,
    Risk,
    TransactionState,
)
from windowsoptimizerabso.domain.state import (
    CapturedState,
    FileState,
    RegistryValueState,
    ScheduledTaskState,
    ServiceState,
    StateError,
    StateSet,
)


# ---------------------------------------------------------------------------
# codecs (CORE-007, CORE-009, BAK-005)
# ---------------------------------------------------------------------------

BINARY_MASK = b"\x90\x12\x03\x80\x10\x00\x00\x00"


def test_binary_registry_data_round_trips():
    """CORE-007: json.dumps(bytes) raises, so the baseline could not persist REG_BINARY at all.

    Worse, it raised at session-save time -- after the mutation had already happened.
    """
    encoded = codecs.dumps({"UserPreferencesMask": BINARY_MASK})
    assert codecs.loads(encoded)["UserPreferencesMask"] == BINARY_MASK


@pytest.mark.parametrize(
    "value",
    [
        b"",
        b"\x00\xff\xfe",
        BINARY_MASK,
        "plain string",
        "unicode: ✓ 日本語 \\ \" '",
        0,
        0xFFFFFFFF,
        -1,
        True,
        False,
        None,
        ["a", 1, b"\x01"],
        ("multi", "sz", "value"),
        {"nested": {"deep": b"\x02"}},
    ],
)
def test_values_round_trip_exactly(value):
    assert codecs.loads(codecs.dumps(value)) == value


def test_a_payload_containing_the_reserved_key_cannot_forge_a_type():
    """A registry string value that looks like the tagged encoding must not decode as bytes."""
    hostile = {"__type__": "bytes", "data": "AAAA"}
    decoded = codecs.loads(codecs.dumps(hostile))
    assert decoded == hostile
    assert not isinstance(decoded, bytes)


def test_naive_datetimes_are_refused():
    """SYS-004: a naive timestamp is ambiguous, and this data drives drift decisions."""
    with pytest.raises(ValueError):
        codecs.dumps(datetime(2026, 1, 1, 12, 0, 0))


def test_aware_datetimes_round_trip():
    moment = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert codecs.loads(codecs.dumps(moment)) == moment


def test_canonical_form_is_order_independent():
    assert codecs.digest({"a": 1, "b": 2}) == codecs.digest({"b": 2, "a": 1})


def test_digests_distinguish_lookalike_values():
    """1 is not True, b"\\x01" is not [1], and "1" is not 1."""
    digests = {codecs.digest(v) for v in [1, True, b"\x01", [1], "1"]}
    assert len(digests) == 5


def test_digest_is_sha256_not_md5():
    """BAK-005: the baseline checksummed backups with MD5 and never verified them."""
    assert len(codecs.digest("x")) == 64


def test_corrupt_state_is_refused_not_defaulted():
    """A journal that returns a plausible-but-wrong pre-state writes wrong values to a machine."""
    with pytest.raises(codecs.DecodeError):
        codecs.loads("{not json")
    with pytest.raises(codecs.DecodeError):
        codecs.loads('{"__type__": "bytes", "data": "not base64!!"}')
    with pytest.raises(codecs.DecodeError):
        codecs.loads('{"__type__": "nonsense", "data": 1}')


def test_unencodable_types_raise_rather_than_stringify():
    with pytest.raises(TypeError):
        codecs.dumps(object())


# ---------------------------------------------------------------------------
# Captured state (REG-001, REG-002, REG-005, PRV-007)
# ---------------------------------------------------------------------------

def test_registry_state_records_the_original_type():
    """REG-001: rollback captured the *target* type, so restoring a REG_SZ wrote a REG_DWORD."""
    state = RegistryValueState(
        hive="HKLM", subkey=r"SOFTWARE\Test", value_name="Setting",
        presence=Presence.PRESENT, value_type="REG_SZ", data="original",
    )
    restored = CapturedState.deserialise(state.serialise())
    assert restored.value_type == "REG_SZ"
    assert restored.data == "original"


def test_present_registry_value_must_declare_its_type():
    """REG-005: defaulting an unknown type to string silently corrupts binary values."""
    with pytest.raises(StateError):
        RegistryValueState(
            hive="HKLM", subkey="S", value_name="V", presence=Presence.PRESENT, data=1,
        )


def test_absent_and_container_absent_are_distinct_states():
    """`None` may not mean "did not exist": deleting and blanking roll back differently."""
    absent = RegistryValueState(hive="HKLM", subkey="S", value_name="V", presence=Presence.ABSENT)
    no_key = RegistryValueState(
        hive="HKLM", subkey="S", value_name="V", presence=Presence.CONTAINER_ABSENT
    )
    empty = RegistryValueState(
        hive="HKLM", subkey="S", value_name="V", presence=Presence.PRESENT,
        value_type="REG_SZ", data="",
    )
    assert not absent.equals(no_key)
    assert not absent.equals(empty)
    assert len({absent.digest, no_key.digest, empty.digest}) == 3


def test_absent_state_may_not_carry_data():
    with pytest.raises(StateError):
        RegistryValueState(
            hive="HKLM", subkey="S", value_name="V", presence=Presence.ABSENT,
            value_type="REG_SZ", data="x",
        )


def test_user_scoped_registry_state_requires_a_target_sid():
    """PRV-007/VIS-005: an elevated process's HKCU is the elevating account's hive."""
    with pytest.raises(StateError) as excinfo:
        RegistryValueState(
            hive="HKCU", subkey=r"Control Panel\Desktop", value_name="X",
            presence=Presence.PRESENT, value_type="REG_DWORD", data=1,
        )
    assert "SID" in str(excinfo.value)

    RegistryValueState(
        hive="HKCU", subkey=r"Control Panel\Desktop", value_name="X",
        presence=Presence.PRESENT, value_type="REG_DWORD", data=1,
        target_sid="S-1-5-21-1001",
    )


def test_registry_view_is_part_of_identity():
    """REG-002: capturing in one view and restoring in another restores a different key."""
    native = RegistryValueState(
        hive="HKLM", subkey="SOFTWARE", value_name="V", presence=Presence.PRESENT,
        value_type="REG_DWORD", data=1, view=RegistryView.NATIVE,
    )
    wow = RegistryValueState(
        hive="HKLM", subkey="SOFTWARE", value_name="V", presence=Presence.PRESENT,
        value_type="REG_DWORD", data=1, view=RegistryView.WOW64_32,
    )
    assert not native.equals(wow)


def test_binary_registry_state_survives_the_journal():
    state = RegistryValueState(
        hive="HKCU", subkey=r"Control Panel\Desktop", value_name="UserPreferencesMask",
        presence=Presence.PRESENT, value_type="REG_BINARY", data=BINARY_MASK,
        target_sid="S-1-5-21-1001",
    )
    restored = CapturedState.deserialise(state.serialise())
    assert restored.equals(state)
    assert restored.data == BINARY_MASK


def test_service_identity_is_case_insensitive():
    """SVC-001: Windows service names are case-insensitive; the baseline's guard was not."""
    assert ServiceState(name="DiagTrack", presence=Presence.ABSENT).key == \
           ServiceState(name="diagtrack", presence=Presence.ABSENT).key


def test_present_service_must_record_start_type_and_run_state():
    """SVC-005: the baseline guessed Manual on restore instead of recording what was there."""
    with pytest.raises(StateError):
        ServiceState(name="DiagTrack", presence=Presence.PRESENT, start_type="auto")


def test_present_file_must_record_a_digest():
    with pytest.raises(StateError):
        FileState(path="C:/x", presence=Presence.PRESENT)


def test_scheduled_task_records_enabled_state():
    with pytest.raises(StateError):
        ScheduledTaskState(task_path=r"\Microsoft\X", presence=Presence.PRESENT)


def test_state_from_an_unknown_codec_version_is_refused():
    blob = codecs.dumps({"kind": "registry_value", "codec_version": 999, "payload": {}})
    with pytest.raises(codecs.DecodeError):
        CapturedState.deserialise(blob)


def test_state_set_reports_what_differs():
    before = StateSet((
        RegistryValueState(hive="HKLM", subkey="S", value_name="A", presence=Presence.PRESENT,
                           value_type="REG_DWORD", data=1),
        RegistryValueState(hive="HKLM", subkey="S", value_name="B", presence=Presence.ABSENT),
    ))
    after = StateSet((
        RegistryValueState(hive="HKLM", subkey="S", value_name="A", presence=Presence.PRESENT,
                           value_type="REG_DWORD", data=2),
        RegistryValueState(hive="HKLM", subkey="S", value_name="B", presence=Presence.ABSENT),
    ))
    assert not before.equals(after)
    differences = before.differences(after)
    assert len(differences) == 1
    assert r"HKLM\S\A" in differences[0]


def test_state_set_round_trips():
    original = StateSet((
        RegistryValueState(hive="HKLM", subkey="S", value_name="A", presence=Presence.PRESENT,
                           value_type="REG_BINARY", data=b"\x01\x02"),
        ServiceState(name="DiagTrack", presence=Presence.PRESENT, start_type="auto", running=True),
    ))
    assert StateSet.deserialise(original.serialise()).equals(original)


# ---------------------------------------------------------------------------
# Enums (CORE-016, CORE-017)
# ---------------------------------------------------------------------------

def test_risk_ordering_is_explicit_not_declaration_order():
    """CORE-017: the baseline ranked risk by list(Enum).index(), and included a CUSTOM member."""
    assert Risk.MINIMAL < Risk.LOW < Risk.MODERATE < Risk.HIGH < Risk.IRREVERSIBLE
    assert not hasattr(Risk, "CUSTOM")
    assert int(Risk.MINIMAL) == 10  # pinned: reordering members must not re-rank operations


@pytest.mark.parametrize(
    ("status", "is_success"),
    [
        (OperationStatus.SUCCEEDED, True),
        (OperationStatus.ROLLBACK_SUCCEEDED, True),
        (OperationStatus.FAILED, False),
        (OperationStatus.PARTIAL, False),
        (OperationStatus.SKIPPED, False),
        (OperationStatus.NOT_APPLICABLE, False),
        (OperationStatus.UNSUPPORTED, False),
        (OperationStatus.REQUIRES_REBOOT, False),
        (OperationStatus.ROLLBACK_PARTIAL, False),
        (OperationStatus.ROLLBACK_FAILED, False),
    ],
)
def test_only_verified_completion_counts_as_success(status, is_success):
    """CORE-016: REQUIRES_REBOOT is not success -- the postcondition has not been verified."""
    assert status.is_success is is_success


@pytest.mark.parametrize(
    "status",
    [OperationStatus.SUCCEEDED, OperationStatus.PARTIAL, OperationStatus.FAILED,
     OperationStatus.REQUIRES_REBOOT],
)
def test_anything_that_crossed_apply_is_a_rollback_candidate(status):
    """A failure mid-write can still have written something."""
    assert status.changed_the_machine


@pytest.mark.parametrize(
    "status", [OperationStatus.SKIPPED, OperationStatus.NOT_APPLICABLE, OperationStatus.UNSUPPORTED]
)
def test_operations_that_never_ran_are_not_rollback_candidates(status):
    assert not status.changed_the_machine


def test_crash_states_are_recognised_as_needing_recovery():
    assert TransactionState.RUNNING.needs_recovery
    assert TransactionState.ROLLING_BACK.needs_recovery
    assert TransactionState.PARTIAL.needs_recovery
    assert not TransactionState.SUCCEEDED.needs_recovery
    assert not TransactionState.ROLLED_BACK.needs_recovery


def test_apply_boundary_is_recognised_from_the_journal():
    """Recovery decides from the last recorded phase whether the machine may have been touched."""
    assert not LifecyclePhase.PLANNED.crossed_apply_boundary
    assert not LifecyclePhase.PRESTATE_DURABLE.crossed_apply_boundary
    assert LifecyclePhase.APPLY_STARTED.crossed_apply_boundary
    assert LifecyclePhase.COMMITTED.crossed_apply_boundary


def test_expiry_helper_uses_timezone_aware_comparison():
    now = datetime.now(timezone.utc)
    assert now + timedelta(minutes=1) > now
