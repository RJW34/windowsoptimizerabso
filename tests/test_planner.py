"""Planner and plan-integrity proof (gate G2).

Evidence for CORE-005 (no applicability model), CORE-006 (no dependency or conflict ordering),
CORE-012 (no immutable plan digest or drift check), SEC-005 (state can change between plan and
apply), REG-004/SEC-003 (a profile must not be able to widen what an operation touches), and
BASE-012 (analysis listed task metadata rather than actual state).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from conftest_operations import (
    USER_SID,
    binary_registry_operation,
    make_environment,
    registry_toggle_operation,
    registry_with,
    seeded_machine,
    service_operation,
)

from windowsoptimizerabso.domain.enums import Presence, Risk
from windowsoptimizerabso.domain.operation import Environment, OperationError
from windowsoptimizerabso.domain.plan import ExecutionPlan, PlanError
from windowsoptimizerabso.domain.state import RegistryValueState
from windowsoptimizerabso.planner.planner import (
    ConflictError,
    Planner,
    Selection,
    summarise_risk,
)

FINGERPRINT = "abc123fingerprint"


def build(machine, *specs, **kwargs):
    registry = registry_with(*specs)
    planner = Planner(registry)
    selections = [Selection(s.operation_id, kwargs.pop("params", {}).get(s.operation_id, {}))
                  for s in specs]
    plan = planner.plan(
        selections,
        environment=kwargs.pop("environment", make_environment(machine)),
        machine_fingerprint=kwargs.pop("machine_fingerprint", FINGERPRINT),
        **kwargs,
    )
    return registry, plan


# ---------------------------------------------------------------------------
# Applicability (CORE-005, BASE-012, PRV-006)
# ---------------------------------------------------------------------------

def test_plan_records_observed_state_not_just_task_metadata():
    """BASE-012: `analyze` listed what the tool could do, not what the machine was."""
    machine = seeded_machine()
    _, plan = build(machine, registry_toggle_operation(machine))
    observed = plan.operations[0].observed_state.states[0]
    assert isinstance(observed, RegistryValueState)
    assert observed.presence is Presence.PRESENT
    assert observed.data == 0


def test_an_already_satisfied_operation_is_kept_but_not_run():
    machine = seeded_machine()
    machine.registry.seed("HKLM", r"SOFTWARE\Test", "Toggle", "REG_DWORD", 1)
    _, plan = build(machine, registry_toggle_operation(machine))

    assert len(plan.operations) == 1
    assert plan.operations[0].applicability.already_satisfied
    assert plan.operations_to_run == ()
    assert plan.is_zero_change


def test_a_zero_change_plan_is_valid_not_an_error():
    """G9: a profile that finds nothing to do is a legitimate outcome, not a failure."""
    machine = seeded_machine()
    machine.registry.seed("HKLM", r"SOFTWARE\Test", "Toggle", "REG_DWORD", 1)
    _, plan = build(machine, registry_toggle_operation(machine))
    assert plan.is_zero_change
    assert "No changes" in summarise_risk(plan)


def test_missing_target_is_not_applicable_rather_than_failed():
    """PRV-006: the baseline counted an absent scheduled task as a failure."""
    machine = seeded_machine()
    _, plan = build(machine, service_operation(machine, "NotInstalledSvc"))
    operation = plan.operations[0]
    assert not operation.applicability.applicable
    assert "not installed" in operation.applicability.reason
    assert plan.operations_to_run == ()


def test_non_windows_is_not_applicable_with_a_stated_reason():
    machine = seeded_machine()
    _, plan = build(
        machine,
        registry_toggle_operation(machine),
        environment=make_environment(machine, os_system="Linux"),
    )
    assert not plan.operations[0].applicability.applicable
    assert "requires Windows" in plan.operations[0].applicability.reason


def test_an_applicability_check_that_raises_yields_not_applicable():
    """Planning must never leave the machine worse off, including when inspection fails."""
    machine = seeded_machine()
    spec = registry_toggle_operation(machine)
    machine.faults.fail("read_value", "Toggle", times=None, category="permission_denied")
    _, plan = build(machine, spec)
    assert not plan.operations[0].applicability.applicable
    assert "could not determine applicability" in plan.operations[0].applicability.reason


# ---------------------------------------------------------------------------
# Parameters: the profile boundary (REG-004, SEC-003)
# ---------------------------------------------------------------------------

def test_a_profile_cannot_pass_an_undeclared_parameter():
    """REG-004/SEC-003: an operation may not accept an arbitrary registry path from a profile."""
    machine = seeded_machine()
    registry = registry_with(registry_toggle_operation(machine))
    planner = Planner(registry)
    with pytest.raises(OperationError) as excinfo:
        planner.plan(
            [Selection("test.registry_toggle", {"subkey": r"SOFTWARE\Microsoft\Windows"})],
            environment=make_environment(machine),
            machine_fingerprint=FINGERPRINT,
        )
    assert "does not accept parameter" in str(excinfo.value)


def test_a_declared_parameter_is_validated():
    machine = seeded_machine()
    registry = registry_with(registry_toggle_operation(machine))
    planner = Planner(registry)
    with pytest.raises(OperationError):
        planner.plan(
            [Selection("test.registry_toggle", {"value": "not an int"})],
            environment=make_environment(machine),
            machine_fingerprint=FINGERPRINT,
        )


def test_an_unregistered_operation_id_is_rejected():
    machine = seeded_machine()
    planner = Planner(registry_with(registry_toggle_operation(machine)))
    with pytest.raises(OperationError) as excinfo:
        planner.plan(
            [Selection("something.invented")],
            environment=make_environment(machine),
            machine_fingerprint=FINGERPRINT,
        )
    assert "cannot introduce one" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Conflicts and dependencies (CORE-006)
# ---------------------------------------------------------------------------

def test_two_operations_writing_the_same_setting_conflict():
    machine = seeded_machine()
    first = registry_toggle_operation(machine, operation_id="test.a", conflict_keys=("hklm/toggle",))
    second = registry_toggle_operation(machine, operation_id="test.b", conflict_keys=("hklm/toggle",))
    with pytest.raises(ConflictError) as excinfo:
        build(machine, first, second)
    assert "both modify" in str(excinfo.value)


def test_dependencies_order_the_plan():
    machine = seeded_machine()
    dependent = registry_toggle_operation(
        machine, operation_id="test.second", depends_on=("test.first",)
    )
    dependency = registry_toggle_operation(machine, operation_id="test.first")
    _, plan = build(machine, dependent, dependency)
    assert [op.operation_id for op in plan.operations] == ["test.first", "test.second"]


def test_a_missing_dependency_is_refused():
    machine = seeded_machine()
    spec = registry_toggle_operation(machine, operation_id="test.x", depends_on=("test.absent",))
    with pytest.raises(ConflictError) as excinfo:
        build(machine, spec)
    assert "not in this plan" in str(excinfo.value)


def test_a_dependency_cycle_is_refused_rather_than_ordered_arbitrarily():
    """Rollback runs this order reversed, so a guessed order produces a wrong rollback order."""
    machine = seeded_machine()
    a = registry_toggle_operation(machine, operation_id="test.a", depends_on=("test.b",))
    b = registry_toggle_operation(machine, operation_id="test.b", depends_on=("test.a",))
    with pytest.raises(ConflictError) as excinfo:
        build(machine, a, b)
    assert "cycle" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Plan integrity (CORE-012, SEC-005)
# ---------------------------------------------------------------------------

def test_plan_round_trips_through_serialisation():
    machine = seeded_machine()
    _, plan = build(machine, registry_toggle_operation(machine), binary_registry_operation(machine))
    restored = ExecutionPlan.deserialise(plan.serialise())
    assert restored.digest == plan.digest
    assert len(restored.operations) == 2
    assert restored.operations[1].observed_state.states[0].data == \
        plan.operations[1].observed_state.states[0].data


def test_editing_a_plan_file_invalidates_it():
    """CORE-012: the thing that was reviewed must be the thing that runs."""
    machine = seeded_machine()
    _, plan = build(machine, registry_toggle_operation(machine))
    tampered = plan.serialise().replace('"value":1', '"value":999')
    if tampered == plan.serialise():
        tampered = plan.serialise().replace(plan.machine_fingerprint, "someone-elses-machine")
    with pytest.raises(PlanError) as excinfo:
        ExecutionPlan.deserialise(tampered)
    assert "digest" in str(excinfo.value)


def test_the_digest_covers_what_will_happen_not_the_prose():
    machine = seeded_machine()
    _, plan = build(machine, registry_toggle_operation(machine))
    reworded = ExecutionPlan(
        plan_id=plan.plan_id,
        created_at=plan.created_at,
        expires_at=plan.expires_at,
        machine_fingerprint=plan.machine_fingerprint,
        target_user_sid=plan.target_user_sid,
        os_build=plan.os_build,
        operations=plan.operations,
        notes=("an added note",),
    )
    assert reworded.digest == plan.digest


def test_changing_a_parameter_changes_the_digest():
    machine = seeded_machine()
    registry = registry_with(registry_toggle_operation(machine))
    planner = Planner(registry)
    env = make_environment(machine)
    now = datetime(2026, 8, 18, tzinfo=timezone.utc)
    one = planner.plan([Selection("test.registry_toggle", {"value": 1})],
                       environment=env, machine_fingerprint=FINGERPRINT, now=now)
    two = planner.plan([Selection("test.registry_toggle", {"value": 2})],
                       environment=env, machine_fingerprint=FINGERPRINT, now=now)
    assert one.digest != two.digest


def test_a_wrong_confirmation_digest_is_refused():
    machine = seeded_machine()
    registry, plan = build(machine, registry_toggle_operation(machine))
    with pytest.raises(PlanError) as excinfo:
        plan.validate_for_execution(
            registry=registry,
            environment=make_environment(machine),
            machine_fingerprint=FINGERPRINT,
            confirmation_digest="0" * 12,
        )
    assert "confirmation digest" in str(excinfo.value)


def test_the_short_digest_is_accepted_for_interactive_confirmation():
    machine = seeded_machine()
    registry, plan = build(machine, registry_toggle_operation(machine))
    plan.validate_for_execution(
        registry=registry,
        environment=make_environment(machine),
        machine_fingerprint=FINGERPRINT,
        confirmation_digest=plan.short_digest,
    )


def test_an_expired_plan_is_refused():
    """SEC-005: state observed an hour ago is not evidence about the machine now."""
    machine = seeded_machine()
    registry, plan = build(machine, registry_toggle_operation(machine),
                           lifetime=timedelta(minutes=5))
    later = datetime.now(timezone.utc) + timedelta(minutes=6)
    with pytest.raises(PlanError) as excinfo:
        plan.validate_for_execution(
            registry=registry,
            environment=make_environment(machine),
            machine_fingerprint=FINGERPRINT,
            confirmation_digest=plan.digest,
            now=later,
        )
    assert "expired" in str(excinfo.value)


def test_a_plan_from_another_machine_is_refused():
    machine = seeded_machine()
    registry, plan = build(machine, registry_toggle_operation(machine))
    with pytest.raises(PlanError) as excinfo:
        plan.validate_for_execution(
            registry=registry,
            environment=make_environment(machine),
            machine_fingerprint="a-different-machine",
            confirmation_digest=plan.digest,
        )
    assert "different machine" in str(excinfo.value)


def test_a_plan_from_another_os_build_is_refused():
    machine = seeded_machine()
    registry, plan = build(machine, registry_toggle_operation(machine))
    with pytest.raises(PlanError) as excinfo:
        plan.validate_for_execution(
            registry=registry,
            environment=make_environment(machine, os_build="19045.1234"),
            machine_fingerprint=FINGERPRINT,
            confirmation_digest=plan.digest,
        )
    assert "OS build" in str(excinfo.value)


def test_an_unelevated_process_cannot_execute_an_admin_plan():
    machine = seeded_machine()
    registry, plan = build(machine, registry_toggle_operation(machine))
    with pytest.raises(PlanError) as excinfo:
        plan.validate_for_execution(
            registry=registry,
            environment=make_environment(machine, is_admin=False),
            machine_fingerprint=FINGERPRINT,
            confirmation_digest=plan.digest,
        )
    assert "administrator" in str(excinfo.value)


def test_a_user_scoped_plan_requires_a_resolved_target_sid():
    """CORE-014: an elevated executor writing HKCU without a SID writes the wrong hive."""
    machine = seeded_machine()
    registry, plan = build(machine, binary_registry_operation(machine))
    with pytest.raises(PlanError) as excinfo:
        plan.validate_for_execution(
            registry=registry,
            environment=Environment(os_system="Windows", os_build=plan.os_build, is_admin=True,
                                    target_user_sid=None),
            machine_fingerprint=FINGERPRINT,
            confirmation_digest=plan.digest,
        )
    assert "target user SID" in str(excinfo.value)


def test_a_plan_with_a_future_schema_version_is_refused():
    machine = seeded_machine()
    registry, plan = build(machine, registry_toggle_operation(machine))
    future = ExecutionPlan(
        plan_id=plan.plan_id, created_at=plan.created_at, expires_at=plan.expires_at,
        machine_fingerprint=plan.machine_fingerprint, target_user_sid=plan.target_user_sid,
        os_build=plan.os_build, operations=plan.operations, schema_version=99,
    )
    with pytest.raises(PlanError) as excinfo:
        future.validate_for_execution(
            registry=registry, environment=make_environment(machine),
            machine_fingerprint=FINGERPRINT, confirmation_digest=future.digest,
        )
    assert "schema version" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Plan presentation
# ---------------------------------------------------------------------------

def test_plan_surfaces_risk_activation_and_reversibility():
    machine = seeded_machine()
    _, plan = build(machine, service_operation(machine), binary_registry_operation(machine))
    assert plan.highest_risk is Risk.HIGH
    assert plan.requires_admin
    assert any(a.value == "explorer_restart" for a in plan.activation_requirements)
    assert plan.irreversible_operations == ()


def test_plan_notes_flag_non_authoritative_evidence():
    machine = seeded_machine()
    spec = registry_toggle_operation(machine)
    object.__setattr__(spec.evidence, "source", "https://some-tweak-blog.example/post")
    _, plan = build(machine, spec)
    assert any("not primary documentation" in note for note in plan.notes)


def test_summarise_risk_states_counts_without_superlatives():
    machine = seeded_machine()
    _, plan = build(machine, service_operation(machine))
    summary = summarise_risk(plan)
    assert "1 operation(s) to run" in summary
    for banned in ["maximum", "blazing", "ultimate", "supercharge"]:
        assert banned not in summary.lower()


def test_user_scoped_plan_records_the_target_sid():
    machine = seeded_machine()
    _, plan = build(machine, binary_registry_operation(machine))
    assert plan.target_user_sid == USER_SID
