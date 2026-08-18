"""Transactional lifecycle proof (gates G3 and G4).

Evidence for CORE-001 (no centralised exact pre-state capture), CORE-002 (no durable atomic
journal), CORE-003 (operations trusted return values instead of verifying), CORE-004 (execution
continued after failure with no coordinated rollback), CORE-011 (no crash recovery), CORE-013
(concurrent processes could race), BASE-004/CORE-010 (rollback was a no-op identified only by
operation name), TST-003 and TST-004 (no fault injection, no exact state-equality assertion).

Everything here runs against the deterministic fake machine. The Windows VM equivalents (gate G6)
are deferred and recorded as such in the work ledger.
"""

from __future__ import annotations

import pytest
from conftest_operations import (
    binary_registry_operation,
    make_environment,
    registry_toggle_operation,
    registry_with,
    seeded_machine,
    service_operation,
)

from windowsoptimizerabso.backends.fake import FakeMachine
from windowsoptimizerabso.cli.exit_codes import ExitCode
from windowsoptimizerabso.domain.enums import (
    LifecyclePhase,
    OperationStatus,
    Presence,
    TransactionState,
)
from windowsoptimizerabso.domain.plan import PlanError
from windowsoptimizerabso.domain.state import RegistryValueState
from windowsoptimizerabso.executor.executor import Executor, ExecutorError
from windowsoptimizerabso.executor.lock import ExecutionLock, LockHeld
from windowsoptimizerabso.journal.sqlite_journal import (
    JournalCorruption,
    JournalError,
    SqliteJournal,
)
from windowsoptimizerabso.planner.planner import Planner, Selection

FINGERPRINT = "test-machine-fingerprint"


@pytest.fixture
def machine() -> FakeMachine:
    return seeded_machine()


@pytest.fixture
def journal(tmp_path) -> SqliteJournal:
    return SqliteJournal(tmp_path / "journal.sqlite3")


def make_executor(registry, journal, tmp_path, **kwargs):
    return Executor(
        registry=registry,
        journal=journal,
        lock_path=tmp_path / "executor.lock",
        machine_fingerprint=FINGERPRINT,
        allow_mutation=True,  # fake backends only; real mutation still passes through safety
        **kwargs,
    )


def plan_for(machine, *specs, params=None):
    registry = registry_with(*specs)
    planner = Planner(registry)
    plan = planner.plan(
        [Selection(s.operation_id, (params or {}).get(s.operation_id, {})) for s in specs],
        environment=make_environment(machine),
        machine_fingerprint=FINGERPRINT,
    )
    return registry, plan


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_apply_changes_the_machine_and_verifies_it(machine, journal, tmp_path):
    registry, plan = plan_for(machine, registry_toggle_operation(machine))
    report = make_executor(registry, journal, tmp_path).apply(
        plan, environment=make_environment(machine), confirmation_digest=plan.digest
    )

    assert report.state is TransactionState.SUCCEEDED
    assert report.exit_code is ExitCode.SUCCESS
    assert report.outcomes[0].status is OperationStatus.SUCCEEDED
    assert report.outcomes[0].verified
    assert machine.registry.read_value("HKLM", r"SOFTWARE\Test", "Toggle").data == 1


def test_a_zero_change_plan_succeeds_without_touching_anything(machine, journal, tmp_path):
    machine.registry.seed("HKLM", r"SOFTWARE\Test", "Toggle", "REG_DWORD", 1)
    registry, plan = plan_for(machine, registry_toggle_operation(machine))
    before = machine.snapshot()

    report = make_executor(registry, journal, tmp_path).apply(
        plan, environment=make_environment(machine), confirmation_digest=plan.digest
    )

    assert report.state is TransactionState.SUCCEEDED
    assert report.outcomes == []
    assert machine.snapshot() == before


def test_journal_records_every_lifecycle_phase_in_order(machine, journal, tmp_path):
    registry, plan = plan_for(machine, registry_toggle_operation(machine))
    report = make_executor(registry, journal, tmp_path).apply(
        plan, environment=make_environment(machine), confirmation_digest=plan.digest
    )

    phases = [e["phase"] for e in journal.events(report.transaction_id) if e["phase"]]
    assert phases == [
        LifecyclePhase.PRESTATE_CAPTURED.value,
        LifecyclePhase.PRESTATE_DURABLE.value,
        LifecyclePhase.APPLY_STARTED.value,
        LifecyclePhase.APPLY_RETURNED.value,
        LifecyclePhase.POSTSTATE_VERIFIED.value,
        LifecyclePhase.COMMITTED.value,
    ]


def test_prestate_is_durable_before_the_mutating_call(machine, journal, tmp_path):
    """CORE-002: the ordering that makes a crash mid-apply recoverable."""
    registry, plan = plan_for(machine, registry_toggle_operation(machine))
    report = make_executor(registry, journal, tmp_path).apply(
        plan, environment=make_environment(machine), confirmation_digest=plan.digest
    )

    ordered = [e["phase"] for e in journal.events(report.transaction_id) if e["phase"]]
    assert ordered.index(LifecyclePhase.PRESTATE_DURABLE.value) < \
           ordered.index(LifecyclePhase.APPLY_STARTED.value)


def test_captured_prestate_survives_the_journal_exactly(machine, journal, tmp_path):
    """The REG_BINARY case the baseline could not serialise at all (CORE-007)."""
    original = machine.registry.read_value(
        "HKCU", r"Control Panel\Desktop", "UserPreferencesMask",
        target_sid=machine.identity.interactive_user_sid(),
    )
    registry, plan = plan_for(machine, binary_registry_operation(machine))
    report = make_executor(registry, journal, tmp_path).apply(
        plan, environment=make_environment(machine), confirmation_digest=plan.digest
    )

    stored = journal.get_prestate(report.transaction_id, 0)
    assert stored.states[0].equals(original)
    assert stored.states[0].data == b"\x9e\x1e\x07\x80\x12\x00\x00\x00"


# ---------------------------------------------------------------------------
# Exact rollback (TST-004, BASE-004, CORE-010)
# ---------------------------------------------------------------------------

def test_rollback_restores_the_machine_exactly(machine, journal, tmp_path):
    """TST-004: whole-machine equality, not just "the operation reported success"."""
    before = machine.snapshot()
    registry, plan = plan_for(machine, registry_toggle_operation(machine),
                              binary_registry_operation(machine))
    executor = make_executor(registry, journal, tmp_path)
    environment = make_environment(machine)

    report = executor.apply(plan, environment=environment, confirmation_digest=plan.digest)
    # One of the two operations needs an Explorer restart before it takes effect, so the
    # transaction is truthfully REBOOT_PENDING rather than SUCCEEDED (defect VIS-006).
    assert report.state is TransactionState.REBOOT_PENDING
    assert report.exit_code is ExitCode.REBOOT_REQUIRED
    assert machine.snapshot() != before

    rollback = executor.rollback(report.transaction_id, environment=environment)

    assert rollback.state is TransactionState.ROLLED_BACK
    assert machine.snapshot() == before
    assert all(o.verified for o in rollback.rollback_outcomes)
    assert rollback.residual_drift == []


def test_rollback_runs_in_reverse_order(machine, journal, tmp_path):
    first = registry_toggle_operation(machine, operation_id="test.first")
    second = registry_toggle_operation(
        machine, operation_id="test.second", value_name="Second", depends_on=("test.first",)
    )
    machine.registry.seed("HKLM", r"SOFTWARE\Test", "Second", "REG_DWORD", 0)

    registry, plan = plan_for(machine, first, second)
    executor = make_executor(registry, journal, tmp_path)
    environment = make_environment(machine)
    report = executor.apply(plan, environment=environment, confirmation_digest=plan.digest)

    rollback = executor.rollback(report.transaction_id, environment=environment)
    assert [o.operation_id for o in rollback.rollback_outcomes] == ["test.second", "test.first"]


def test_rollback_restores_an_absent_value_by_deleting_it(machine, journal, tmp_path):
    """A value that did not exist must not come back as an empty one."""
    machine.registry.write_value(RegistryValueState(
        hive="HKLM", subkey=r"SOFTWARE\Test", value_name="Toggle", presence=Presence.ABSENT
    ))
    before = machine.snapshot()

    registry, plan = plan_for(machine, registry_toggle_operation(machine))
    executor = make_executor(registry, journal, tmp_path)
    environment = make_environment(machine)
    report = executor.apply(plan, environment=environment, confirmation_digest=plan.digest)
    assert machine.registry.read_value("HKLM", r"SOFTWARE\Test", "Toggle").presence is Presence.PRESENT

    executor.rollback(report.transaction_id, environment=environment)

    assert machine.registry.read_value("HKLM", r"SOFTWARE\Test", "Toggle").presence is Presence.ABSENT
    assert machine.snapshot() == before


def test_rollback_is_idempotent(machine, journal, tmp_path):
    before = machine.snapshot()
    registry, plan = plan_for(machine, registry_toggle_operation(machine))
    executor = make_executor(registry, journal, tmp_path)
    environment = make_environment(machine)
    report = executor.apply(plan, environment=environment, confirmation_digest=plan.digest)

    first = executor.rollback(report.transaction_id, environment=environment)
    second = executor.rollback(report.transaction_id, environment=environment)

    assert first.state is second.state is TransactionState.ROLLED_BACK
    assert machine.snapshot() == before


def test_a_failed_rollback_is_reported_as_failed_not_as_success(machine, journal, tmp_path):
    """BASE-004: the defect this whole layer exists to remove."""
    registry, plan = plan_for(machine, registry_toggle_operation(machine))
    executor = make_executor(registry, journal, tmp_path)
    environment = make_environment(machine)
    report = executor.apply(plan, environment=environment, confirmation_digest=plan.digest)

    machine.faults.fail("write_value", "Toggle", times=None, category="permission_denied")
    rollback = executor.rollback(report.transaction_id, environment=environment)

    assert rollback.state is TransactionState.ROLLBACK_FAILED
    assert rollback.exit_code is ExitCode.ROLLBACK_FAILED
    assert rollback.residual_drift
    assert "restore failed" in rollback.residual_drift[0]


def test_an_unverifiable_rollback_is_partial_not_complete(machine, journal, tmp_path):
    """A restore whose result does not match the capture must say so."""
    registry, plan = plan_for(machine, registry_toggle_operation(machine))
    executor = make_executor(registry, journal, tmp_path)
    environment = make_environment(machine)
    report = executor.apply(plan, environment=environment, confirmation_digest=plan.digest)

    # The restore call "succeeds" but the machine ends up somewhere else entirely.
    machine.faults.fail("write_value", "Toggle", after_effect=True, times=None,
                        category="io_error", message="write lost")
    rollback = executor.rollback(report.transaction_id, environment=environment)

    assert rollback.state in {TransactionState.ROLLBACK_FAILED, TransactionState.ROLLBACK_PARTIAL}
    assert rollback.exit_code is ExitCode.ROLLBACK_FAILED
    assert rollback.residual_drift


def test_corrupt_prestate_refuses_to_restore(machine, journal, tmp_path):
    """A journal that returns a wrong pre-state would write wrong values to a live machine."""
    registry, plan = plan_for(machine, registry_toggle_operation(machine))
    executor = make_executor(registry, journal, tmp_path)
    environment = make_environment(machine)
    report = executor.apply(plan, environment=environment, confirmation_digest=plan.digest)

    with journal.transaction() as cursor:
        cursor.execute(
            "UPDATE operations SET prestate_digest='0'*64 WHERE transaction_id=?",
            (report.transaction_id,),
        )

    with pytest.raises(JournalCorruption):
        journal.get_prestate(report.transaction_id, 0)

    rollback = executor.rollback(report.transaction_id, environment=environment)
    assert rollback.state is TransactionState.ROLLBACK_FAILED
    assert "NOT reverted" in rollback.residual_drift[0]


# ---------------------------------------------------------------------------
# Failure handling (CORE-004)
# ---------------------------------------------------------------------------

def test_a_failure_stops_the_run_and_reverses_what_landed(machine, journal, tmp_path):
    """CORE-004: the baseline logged the error and carried on to the next operation."""
    before = machine.snapshot()
    first = registry_toggle_operation(machine, operation_id="test.first")
    second = registry_toggle_operation(
        machine, operation_id="test.second", value_name="Second"
    )
    third = registry_toggle_operation(machine, operation_id="test.third", value_name="Third")
    machine.registry.seed("HKLM", r"SOFTWARE\Test", "Second", "REG_DWORD", 0)
    machine.registry.seed("HKLM", r"SOFTWARE\Test", "Third", "REG_DWORD", 0)
    before = machine.snapshot()

    registry, plan = plan_for(machine, first, second, third)
    machine.faults.fail("write_value", "Second", category="permission_denied")

    report = make_executor(registry, journal, tmp_path).apply(
        plan, environment=make_environment(machine), confirmation_digest=plan.digest
    )

    assert report.state is TransactionState.ROLLED_BACK
    assert [o.operation_id for o in report.outcomes] == ["test.first", "test.second"]
    assert "test.third" not in [o.operation_id for o in report.outcomes]
    assert machine.snapshot() == before, "the machine must be back where it started"


def test_an_operation_that_cannot_be_verified_is_partial_not_successful(machine, journal, tmp_path):
    """CORE-003: a returned success is not evidence that the postcondition holds."""
    spec = registry_toggle_operation(machine)
    registry, plan = plan_for(machine, spec)
    # The write silently does nothing: apply returns, verification fails.
    machine.faults.fail("write_value", "Toggle", after_effect=True, category="io_error")

    report = make_executor(registry, journal, tmp_path).apply(
        plan, environment=make_environment(machine), confirmation_digest=plan.digest
    )
    assert report.outcomes[0].status is not OperationStatus.SUCCEEDED
    assert report.exit_code is not ExitCode.SUCCESS


def test_a_service_dependency_refusal_surfaces_as_a_categorised_failure(machine, journal, tmp_path):
    from windowsoptimizerabso.domain.state import ServiceState

    machine.services.seed(ServiceState(
        name="Dependent", presence=Presence.PRESENT, start_type="auto", running=True,
        dependencies=("DiagTrack",),
    ))
    registry, plan = plan_for(machine, service_operation(machine))
    report = make_executor(registry, journal, tmp_path).apply(
        plan, environment=make_environment(machine), confirmation_digest=plan.digest
    )

    assert report.outcomes[0].status is OperationStatus.FAILED
    assert report.outcomes[0].error_category == "busy"


# ---------------------------------------------------------------------------
# Drift (CORE-012, SEC-005)
# ---------------------------------------------------------------------------

def test_state_changing_between_plan_and_apply_prevents_the_change(machine, journal, tmp_path):
    registry, plan = plan_for(machine, registry_toggle_operation(machine))

    # Something else edits the value after the plan was built.
    machine.registry.write_value(RegistryValueState(
        hive="HKLM", subkey=r"SOFTWARE\Test", value_name="Toggle", presence=Presence.PRESENT,
        value_type="REG_DWORD", data=7,
    ))
    after_edit = machine.snapshot()

    report = make_executor(registry, journal, tmp_path).apply(
        plan, environment=make_environment(machine), confirmation_digest=plan.digest
    )

    assert report.outcomes[0].status is OperationStatus.SKIPPED
    assert report.outcomes[0].error_category == "drift"
    assert "re-plan" in report.outcomes[0].detail
    assert machine.snapshot() == after_edit, "a drifted operation must not be applied"


def test_drift_in_one_operation_does_not_apply_the_rest(machine, journal, tmp_path):
    first = registry_toggle_operation(machine, operation_id="test.first")
    second = registry_toggle_operation(machine, operation_id="test.second", value_name="Second")
    machine.registry.seed("HKLM", r"SOFTWARE\Test", "Second", "REG_DWORD", 0)

    registry, plan = plan_for(machine, first, second)
    machine.registry.write_value(RegistryValueState(
        hive="HKLM", subkey=r"SOFTWARE\Test", value_name="Toggle", presence=Presence.PRESENT,
        value_type="REG_DWORD", data=9,
    ))

    report = make_executor(registry, journal, tmp_path).apply(
        plan, environment=make_environment(machine), confirmation_digest=plan.digest
    )
    assert report.outcomes[0].status is OperationStatus.SKIPPED
    assert len(report.outcomes) == 1
    assert machine.registry.read_value("HKLM", r"SOFTWARE\Test", "Second").data == 0


def test_a_forged_confirmation_digest_never_reaches_the_machine(machine, journal, tmp_path):
    registry, plan = plan_for(machine, registry_toggle_operation(machine))
    before = machine.snapshot()
    with pytest.raises(PlanError):
        make_executor(registry, journal, tmp_path).apply(
            plan, environment=make_environment(machine), confirmation_digest="deadbeef"
        )
    assert machine.snapshot() == before
    assert journal.list_transactions() == ()


# ---------------------------------------------------------------------------
# Crash recovery (CORE-011)
# ---------------------------------------------------------------------------

def test_an_interrupted_transaction_is_found_and_reversed(machine, journal, tmp_path):
    """The crash case: the mutation landed, the process died before recording the result."""
    before = machine.snapshot()
    registry, plan = plan_for(machine, registry_toggle_operation(machine))
    executor = make_executor(registry, journal, tmp_path)
    environment = make_environment(machine)

    # Simulate a crash *after* the write, before the phase transition that records it.
    machine.faults.fail("write_value", "Toggle", after_effect=True, category="io_error",
                        message="process died")
    report = executor.apply(plan, environment=environment, confirmation_digest=plan.digest)

    # The executor rolled back in-band; force the transaction back to an interrupted state to
    # exercise the out-of-band recovery path a real crash would leave behind.
    journal.set_transaction_state(report.transaction_id, TransactionState.RUNNING)
    machine.faults.clear()
    machine.registry.write_value(RegistryValueState(
        hive="HKLM", subkey=r"SOFTWARE\Test", value_name="Toggle", presence=Presence.PRESENT,
        value_type="REG_DWORD", data=1,
    ))

    recovered = executor.recover(environment=environment)

    assert len(recovered) == 1
    assert recovered[0].state is TransactionState.ROLLED_BACK
    assert machine.snapshot() == before


def test_a_new_plan_is_refused_while_a_transaction_is_incomplete(machine, journal, tmp_path):
    registry, plan = plan_for(machine, registry_toggle_operation(machine))
    executor = make_executor(registry, journal, tmp_path)
    environment = make_environment(machine)
    report = executor.apply(plan, environment=environment, confirmation_digest=plan.digest)
    journal.set_transaction_state(report.transaction_id, TransactionState.RUNNING)

    _, second_plan = plan_for(machine, registry_toggle_operation(machine))
    with pytest.raises(ExecutorError) as excinfo:
        executor.apply(second_plan, environment=environment,
                       confirmation_digest=second_plan.digest)
    assert "recover" in str(excinfo.value)


def test_incomplete_transactions_are_identified_by_state(journal):
    transaction_id = journal.begin_transaction(
        plan_id="p", plan_digest="d", machine_fingerprint=FINGERPRINT
    )
    journal.set_transaction_state(transaction_id, TransactionState.RUNNING)
    assert [t.transaction_id for t in journal.incomplete_transactions()] == [transaction_id]

    journal.set_transaction_state(transaction_id, TransactionState.SUCCEEDED)
    assert journal.incomplete_transactions() == ()


def test_an_operation_past_apply_started_is_treated_as_possibly_mutated(journal):
    """No result recorded does not mean nothing happened."""
    from windowsoptimizerabso.domain.state import StateSet

    transaction_id = journal.begin_transaction(
        plan_id="p", plan_digest="d", machine_fingerprint=FINGERPRINT
    )
    journal.record_prestate(transaction_id, 0, "test.op", StateSet())
    assert not journal.get_operations(transaction_id)[0].may_have_mutated

    journal.record_phase(transaction_id, 0, LifecyclePhase.APPLY_STARTED)
    assert journal.get_operations(transaction_id)[0].may_have_mutated


# ---------------------------------------------------------------------------
# Journal integrity (BAK-006, CORE-008, CORE-009)
# ---------------------------------------------------------------------------

def test_a_phase_cannot_be_recorded_before_prestate(journal):
    """Ordering is enforced, so no mutation can be journalled without its undo information."""
    transaction_id = journal.begin_transaction(
        plan_id="p", plan_digest="d", machine_fingerprint=FINGERPRINT
    )
    with pytest.raises(JournalError) as excinfo:
        journal.record_phase(transaction_id, 0, LifecyclePhase.APPLY_STARTED)
    assert "pre-state must be recorded" in str(excinfo.value)


def test_a_failed_journal_write_leaves_no_partial_row(journal):
    """BAK-006: the baseline's non-atomic index write turned corruption into empty history."""
    transaction_id = journal.begin_transaction(
        plan_id="p", plan_digest="d", machine_fingerprint=FINGERPRINT
    )
    with pytest.raises(RuntimeError):
        with journal.transaction() as cursor:
            cursor.execute(
                "UPDATE transactions SET state='running' WHERE transaction_id=?", (transaction_id,)
            )
            raise RuntimeError("interrupted mid-write")

    assert journal.get_transaction(transaction_id).state is TransactionState.PREPARED


def test_journal_survives_being_reopened(tmp_path):
    """Reopening after a crash must see everything that was committed."""
    path = tmp_path / "journal.sqlite3"
    first = SqliteJournal(path)
    transaction_id = first.begin_transaction(
        plan_id="p", plan_digest="d", machine_fingerprint=FINGERPRINT
    )
    first.set_transaction_state(transaction_id, TransactionState.RUNNING)
    first.close()

    second = SqliteJournal(path)
    assert second.get_transaction(transaction_id).state is TransactionState.RUNNING
    assert [t.transaction_id for t in second.incomplete_transactions()] == [transaction_id]


def test_a_journal_from_a_newer_schema_is_refused(tmp_path):
    path = tmp_path / "journal.sqlite3"
    journal = SqliteJournal(path)
    with journal.transaction() as cursor:
        cursor.execute("UPDATE journal_meta SET value='99' WHERE key='schema_version'")
    journal.close()

    with pytest.raises(JournalError) as excinfo:
        SqliteJournal(path)
    assert "schema version" in str(excinfo.value)


def test_journal_uses_write_ahead_logging(journal):
    mode = journal._connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


# ---------------------------------------------------------------------------
# Concurrency (CORE-013)
# ---------------------------------------------------------------------------

def test_two_executors_cannot_run_at_once(tmp_path):
    lock_path = tmp_path / "executor.lock"
    with ExecutionLock(lock_path):
        with pytest.raises(LockHeld) as excinfo:
            ExecutionLock(lock_path).acquire()
        assert "already applying" in str(excinfo.value)


def test_the_lock_is_released_on_the_way_out(tmp_path):
    lock_path = tmp_path / "executor.lock"
    with ExecutionLock(lock_path):
        pass
    ExecutionLock(lock_path).acquire().release()


def test_the_lock_is_released_even_when_apply_raises(machine, journal, tmp_path):
    registry, plan = plan_for(machine, registry_toggle_operation(machine))
    executor = make_executor(registry, journal, tmp_path)
    with pytest.raises(PlanError):
        executor.apply(plan, environment=make_environment(machine), confirmation_digest="wrong")
    ExecutionLock(tmp_path / "executor.lock").acquire().release()


def test_a_stale_lock_from_a_dead_process_is_broken(tmp_path):
    import json

    lock_path = tmp_path / "executor.lock"
    lock_path.write_text(json.dumps({"pid": 999_999_999, "acquired_at": "2026-01-01T00:00:00Z"}))
    ExecutionLock(lock_path).acquire().release()


def test_an_unreadable_lock_is_treated_as_held_not_as_stale(tmp_path):
    """Fail closed: an unparseable lock file must not be assumed abandoned."""
    lock_path = tmp_path / "executor.lock"
    lock_path.write_text("not json at all")
    with pytest.raises(LockHeld):
        ExecutionLock(lock_path).acquire()


def test_a_live_holder_is_never_broken(tmp_path):
    import json
    import os

    lock_path = tmp_path / "executor.lock"
    lock_path.write_text(json.dumps({"pid": os.getpid(), "acquired_at": "2026-01-01T00:00:00Z"}))
    with pytest.raises(LockHeld):
        ExecutionLock(lock_path).acquire()


# ---------------------------------------------------------------------------
# Exit-code mapping (BASE-013)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (TransactionState.SUCCEEDED, ExitCode.SUCCESS),
        (TransactionState.PARTIAL, ExitCode.PARTIAL),
        (TransactionState.FAILED, ExitCode.APPLY_FAILED),
        (TransactionState.ROLLBACK_PARTIAL, ExitCode.ROLLBACK_FAILED),
        (TransactionState.ROLLBACK_FAILED, ExitCode.ROLLBACK_FAILED),
        (TransactionState.RECOVERY_REQUIRED, ExitCode.RECOVERY_REQUIRED),
        (TransactionState.REBOOT_PENDING, ExitCode.REBOOT_REQUIRED),
    ],
)
def test_transaction_state_maps_to_the_documented_exit_code(state, expected):
    from windowsoptimizerabso.executor.executor import ExecutionReport

    report = ExecutionReport(transaction_id="t", plan_id="p", state=state)
    assert report.exit_code is expected


def test_no_partial_outcome_can_report_success():
    """The invariant behind the whole exit-code table."""
    from windowsoptimizerabso.executor.executor import ExecutionReport

    for state in TransactionState:
        report = ExecutionReport(transaction_id="t", plan_id="p", state=state)
        if state is not TransactionState.SUCCEEDED:
            assert report.exit_code is not ExitCode.SUCCESS, state
