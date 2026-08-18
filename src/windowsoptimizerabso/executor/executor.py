"""The transactional executor.

One rule governs everything here: **the machine may not be in a state the journal does not
describe.** Pre-state is captured and made durable before the mutating call, every transition is
journalled, and a failure stops the run and reverses what landed, in reverse order, verifying each
restoration.

Sequence per operation::

    capture -> drift check -> journal PRESTATE_CAPTURED -> fsync (PRESTATE_DURABLE)
      -> journal APPLY_STARTED -> spec.apply -> journal APPLY_RETURNED
      -> verify postcondition -> POSTSTATE_VERIFIED -> COMMITTED

The window between ``APPLY_STARTED`` and ``APPLY_RETURNED`` is the only point at which the machine
can change, and it is bracketed by durable journal entries, so a crash inside it is recoverable:
the phase says the mutation may have landed, and the pre-state to undo it is on disk.

What the baseline did instead: executed every task in sequence, caught exceptions per task, logged
them, continued to the next one, and wrote a session file at the end (defect CORE-004). A failure
halfway left half a machine changed with no coordinated response, and a crash left no record at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from ..backends.protocols import BackendError
from ..cli.exit_codes import ExitCode
from ..domain.enums import (
    ActivationRequirement,
    LifecyclePhase,
    OperationStatus,
    TransactionState,
)
from ..domain.operation import Environment, OperationRegistry, OperationSpec, Outcome
from ..domain.plan import ExecutionPlan
from ..domain.state import StateSet
from ..journal.sqlite_journal import (
    JournalCorruption,
    OperationRecord,
    SqliteJournal,
)
from ..safety import guard_mutation
from .lock import ExecutionLock


class ExecutorError(RuntimeError):
    """The executor could not proceed. The machine is unchanged unless stated otherwise."""


class DriftDetected(ExecutorError):
    """The machine moved between planning and applying (defects CORE-012, SEC-005)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _categorise(error: BaseException) -> str:
    if isinstance(error, BackendError):
        return error.category
    if isinstance(error, PermissionError):
        return "permission_denied"
    if isinstance(error, FileNotFoundError):
        return "not_found"
    if isinstance(error, TimeoutError):
        return "timeout"
    return "unknown"


@dataclass
class ExecutionReport:
    """What happened, in enough detail to be acted on.

    Deliberately not a success boolean plus a message. :attr:`exit_code` derives from the recorded
    facts rather than being set at the call site, so there is one place where "did this work" is
    decided (defect BASE-013).
    """

    transaction_id: str
    plan_id: str
    state: TransactionState
    outcomes: list[Outcome] = field(default_factory=list)
    rollback_outcomes: list[Outcome] = field(default_factory=list)
    residual_drift: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def applied(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.changed]

    @property
    def requires_activation(self) -> tuple[ActivationRequirement, ...]:
        return tuple(sorted(
            {o.activation for o in self.applied if o.activation is not ActivationRequirement.IMMEDIATE},
            key=lambda a: a.value,
        ))

    @property
    def exit_code(self) -> ExitCode:
        """Map the recorded outcome onto the documented CLI contract."""
        if self.state is TransactionState.ROLLBACK_FAILED:
            return ExitCode.ROLLBACK_FAILED
        if self.state is TransactionState.ROLLBACK_PARTIAL:
            return ExitCode.ROLLBACK_FAILED
        if self.state is TransactionState.ROLLED_BACK:
            # The machine is back where it started, but the plan did not succeed.
            return ExitCode.APPLY_FAILED if not self.applied else ExitCode.ROLLBACK_REQUIRED
        if self.state is TransactionState.RECOVERY_REQUIRED:
            return ExitCode.RECOVERY_REQUIRED
        if self.state is TransactionState.PARTIAL:
            return ExitCode.PARTIAL
        if self.state is TransactionState.FAILED:
            return ExitCode.APPLY_FAILED
        if self.state is TransactionState.REBOOT_PENDING:
            return ExitCode.REBOOT_REQUIRED
        if self.state is TransactionState.SUCCEEDED:
            return ExitCode.SUCCESS
        return ExitCode.INTERNAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "plan_id": self.plan_id,
            "state": self.state.value,
            "exit_code": int(self.exit_code),
            "operations": [o.to_dict() for o in self.outcomes],
            "rollback": [o.to_dict() for o in self.rollback_outcomes],
            "residual_drift": list(self.residual_drift),
            "activation_required": [a.value for a in self.requires_activation],
            "detail": self.detail,
        }


class Executor:
    """Applies an approved plan, or reverses one.

    The executor receives a serialised plan, a digest to confirm it, and an allowlisted operation
    registry -- never a script or a raw target. It validates before it touches anything.
    """

    def __init__(
        self,
        *,
        registry: OperationRegistry,
        journal: SqliteJournal,
        lock_path: Path,
        machine_fingerprint: str,
        allow_mutation: bool = False,
    ) -> None:
        self.registry = registry
        self.journal = journal
        self.lock_path = Path(lock_path)
        self.machine_fingerprint = machine_fingerprint
        #: Only true in tests against fake backends, or once containment is lifted for a ported
        #: operation on a disposable Windows VM. Real mutation still passes through
        #: ``safety.guard_mutation`` at the backend, so this cannot widen containment on its own.
        self.allow_mutation = allow_mutation

    # -- apply -------------------------------------------------------------

    def apply(
        self,
        plan: ExecutionPlan,
        *,
        environment: Environment,
        confirmation_digest: str,
        now: Optional[datetime] = None,
    ) -> ExecutionReport:
        """Validate, then apply the plan under lock, rolling back on the first failure."""
        plan.validate_for_execution(
            registry=self.registry,
            environment=environment,
            machine_fingerprint=self.machine_fingerprint,
            confirmation_digest=confirmation_digest,
            now=now,
        )

        outstanding = self.journal.incomplete_transactions()
        if outstanding:
            raise ExecutorError(
                f"{len(outstanding)} incomplete transaction(s) must be recovered before a new plan "
                f"can be applied: {', '.join(t.transaction_id for t in outstanding)}. "
                "Run `winopt recover`."
            )

        with ExecutionLock(self.lock_path):
            return self._apply_locked(plan, environment)

    def _apply_locked(self, plan: ExecutionPlan, environment: Environment) -> ExecutionReport:
        transaction_id = self.journal.begin_transaction(
            plan_id=plan.plan_id,
            plan_digest=plan.digest,
            machine_fingerprint=self.machine_fingerprint,
        )
        report = ExecutionReport(
            transaction_id=transaction_id, plan_id=plan.plan_id, state=TransactionState.RUNNING
        )

        if plan.is_zero_change:
            self.journal.set_transaction_state(
                transaction_id, TransactionState.SUCCEEDED, "zero-change plan"
            )
            report.state = TransactionState.SUCCEEDED
            report.detail = "Nothing to do: every applicable operation was already satisfied."
            return report

        self.journal.set_transaction_state(transaction_id, TransactionState.RUNNING)

        failed = False
        for sequence, planned in enumerate(plan.operations_to_run):
            spec = self.registry.get(planned.operation_id)
            outcome = self._apply_one(
                transaction_id, sequence, spec, planned.parameters, planned.observed_state,
                environment,
            )
            report.outcomes.append(outcome)
            if not outcome.status.is_success and outcome.status is not OperationStatus.REQUIRES_REBOOT:
                failed = True
                report.detail = (
                    f"{planned.operation_id} did not complete "
                    f"({outcome.error_category or outcome.status.value}): {outcome.detail}"
                )
                break

        if not failed:
            self.journal.set_transaction_state(transaction_id, TransactionState.SUCCEEDED)
            report.state = (
                TransactionState.REBOOT_PENDING
                if any(o.status is OperationStatus.REQUIRES_REBOOT for o in report.outcomes)
                else TransactionState.SUCCEEDED
            )
            if report.state is TransactionState.REBOOT_PENDING:
                self.journal.set_transaction_state(transaction_id, TransactionState.REBOOT_PENDING)
            return report

        # CORE-004: a failure stops the run and reverses what landed, rather than continuing to
        # the next operation and leaving a half-configured machine behind.
        self.journal.set_transaction_state(
            transaction_id, TransactionState.ROLLBACK_PENDING, report.detail
        )
        self._rollback_transaction(transaction_id, environment, report)
        return report

    def _apply_one(
        self,
        transaction_id: str,
        sequence: int,
        spec: OperationSpec,
        params: dict[str, Any],
        planned_state: StateSet,
        environment: Environment,
    ) -> Outcome:
        started = _now()

        def outcome(status: OperationStatus, **kwargs: Any) -> Outcome:
            return Outcome(
                operation_id=spec.operation_id,
                status=status,
                started_at=started,
                finished_at=_now(),
                applicability=kwargs.pop("applicability", spec.check_applicability(
                    env=environment, params=params)),
                activation=spec.activation,
                **kwargs,
            )

        # 1. Re-read state and refuse if the machine moved since planning.
        try:
            captured = spec.capture(env=environment, params=params)
        except Exception as error:  # noqa: BLE001 - categorised, never swallowed
            return outcome(
                OperationStatus.FAILED,
                error_category=_categorise(error),
                detail=f"could not capture pre-state: {error}",
            )

        if not captured.equals(planned_state):
            differences = "; ".join(planned_state.differences(captured)) or "state changed"
            return outcome(
                OperationStatus.SKIPPED,
                error_category="drift",
                detail=(
                    f"machine state changed since planning ({differences}). Nothing was applied; "
                    "re-plan against current state."
                ),
                observed_before=captured,
            )

        # 2. Durable pre-state before the mutating call.
        self.journal.record_prestate(transaction_id, sequence, spec.operation_id, captured)
        self.journal.mark_prestate_durable(transaction_id, sequence)

        # 3. Apply.
        self.journal.record_phase(transaction_id, sequence, LifecyclePhase.APPLY_STARTED)
        if not self.allow_mutation:
            guard_mutation(f"apply {spec.operation_id}")
        try:
            spec.apply(env=environment, params=params, captured=captured)
        except Exception as error:  # noqa: BLE001
            self.journal.record_phase(
                transaction_id, sequence, LifecyclePhase.APPLY_RETURNED,
                status=OperationStatus.FAILED, error_category=_categorise(error), detail=str(error),
            )
            # FAILED, not SKIPPED: the call may have partially landed before raising, so this
            # operation stays a rollback candidate.
            return outcome(
                OperationStatus.FAILED,
                error_category=_categorise(error),
                detail=str(error),
                observed_before=captured,
                changed=True,
            )
        self.journal.record_phase(transaction_id, sequence, LifecyclePhase.APPLY_RETURNED)

        # 4. Verify the postcondition. A returned success is not evidence (defect CORE-003).
        try:
            observed_after = spec.capture(env=environment, params=params)
            verified = self._verify(spec, environment, params)
        except Exception as error:  # noqa: BLE001
            return outcome(
                OperationStatus.PARTIAL,
                error_category=_categorise(error),
                detail=f"applied, but the result could not be verified: {error}",
                observed_before=captured,
                changed=True,
            )

        if not verified:
            self.journal.record_phase(
                transaction_id, sequence, LifecyclePhase.APPLY_RETURNED,
                status=OperationStatus.PARTIAL, error_category="verification_failed",
                detail="postcondition not satisfied after apply",
            )
            return outcome(
                OperationStatus.PARTIAL,
                error_category="verification_failed",
                detail="the operation reported success but the postcondition is not satisfied",
                observed_before=captured,
                observed_after=observed_after,
                changed=True,
            )

        self.journal.record_phase(transaction_id, sequence, LifecyclePhase.POSTSTATE_VERIFIED)

        if spec.activation is not ActivationRequirement.IMMEDIATE:
            # The state postcondition holds, but the user-visible effect does not until Explorer
            # restarts, the user logs off, or the machine reboots. Reporting this as done is the
            # defect VIS-006 describes: the setting is correct and nothing has changed yet.
            self.journal.record_phase(
                transaction_id, sequence, LifecyclePhase.COMMITTED,
                status=OperationStatus.REQUIRES_REBOOT,
                detail=f"activation required: {spec.activation.value}",
            )
            return outcome(
                OperationStatus.REQUIRES_REBOOT,
                detail=f"applied and verified; {spec.activation.value} required before it takes effect",
                observed_before=captured,
                observed_after=observed_after,
                verified=True,
                changed=not captured.equals(observed_after),
            )

        self.journal.record_phase(
            transaction_id, sequence, LifecyclePhase.COMMITTED, status=OperationStatus.SUCCEEDED
        )
        return outcome(
            OperationStatus.SUCCEEDED,
            observed_before=captured,
            observed_after=observed_after,
            verified=True,
            changed=not captured.equals(observed_after),
        )

    @staticmethod
    def _verify(spec: OperationSpec, environment: Environment, params: dict[str, Any]) -> bool:
        """Whether the operation's desired state is now true.

        Uses the operation's own applicability check: ``already_satisfied`` *is* the postcondition,
        which keeps one definition of "the machine is in the desired state" instead of two that can
        drift apart.
        """
        return spec.check_applicability(env=environment, params=params).already_satisfied

    # -- rollback ----------------------------------------------------------

    def rollback(
        self, transaction_id: str, *, environment: Environment
    ) -> ExecutionReport:
        """Reverse a previously applied transaction.

        Idempotent: rolling back an already rolled-back transaction restores the same captured
        state again and verifies it, rather than failing or double-applying.
        """
        record = self.journal.get_transaction(transaction_id)
        report = ExecutionReport(
            transaction_id=transaction_id, plan_id=record.plan_id, state=record.state
        )
        with ExecutionLock(self.lock_path):
            self._rollback_transaction(transaction_id, environment, report)
        return report

    def _rollback_transaction(
        self, transaction_id: str, environment: Environment, report: ExecutionReport
    ) -> None:
        self.journal.set_transaction_state(transaction_id, TransactionState.ROLLING_BACK)

        records = [r for r in self.journal.get_operations(transaction_id) if r.may_have_mutated]

        succeeded = 0
        failed = 0
        # Reverse order: a later operation may depend on an earlier one, so undoing in the same
        # order as applying can fail or restore into a state the next restore then breaks.
        for record in sorted(records, key=lambda r: r.sequence, reverse=True):
            outcome = self._restore_one(transaction_id, record, environment)
            report.rollback_outcomes.append(outcome)
            report.residual_drift.extend(outcome.residual_drift)
            if outcome.status is OperationStatus.ROLLBACK_SUCCEEDED:
                succeeded += 1
            else:
                failed += 1

        if failed == 0:
            state = TransactionState.ROLLED_BACK
        elif succeeded == 0:
            state = TransactionState.ROLLBACK_FAILED
        else:
            state = TransactionState.ROLLBACK_PARTIAL

        self.journal.set_transaction_state(transaction_id, state)
        report.state = state

    def _restore_one(
        self, transaction_id: str, record: OperationRecord, environment: Environment
    ) -> Outcome:
        started = _now()
        spec = self.registry.get(record.operation_id)

        def outcome(status: OperationStatus, **kwargs: Any) -> Outcome:
            from ..domain.operation import Applicability

            return Outcome(
                operation_id=record.operation_id,
                status=status,
                started_at=started,
                finished_at=_now(),
                applicability=Applicability.yes(),
                activation=spec.activation,
                **kwargs,
            )

        try:
            captured = self.journal.get_prestate(transaction_id, record.sequence)
        except JournalCorruption as error:
            return outcome(
                OperationStatus.ROLLBACK_FAILED,
                error_category="journal_corruption",
                detail=str(error),
                residual_drift=(
                    f"{record.operation_id}: pre-state is unreadable, the change was NOT reverted",
                ),
            )

        self.journal.record_phase(
            transaction_id, record.sequence, LifecyclePhase.ROLLBACK_STARTED
        )
        if not self.allow_mutation:
            guard_mutation(f"rollback {record.operation_id}")

        try:
            spec.restore(env=environment, params={}, captured=captured)
        except Exception as error:  # noqa: BLE001
            self.journal.record_phase(
                transaction_id, record.sequence, LifecyclePhase.ROLLBACK_RETURNED,
                status=OperationStatus.ROLLBACK_FAILED, error_category=_categorise(error),
                detail=str(error),
            )
            return outcome(
                OperationStatus.ROLLBACK_FAILED,
                error_category=_categorise(error),
                detail=str(error),
                residual_drift=(f"{record.operation_id}: restore failed ({error})",),
            )

        self.journal.record_phase(
            transaction_id, record.sequence, LifecyclePhase.ROLLBACK_RETURNED
        )

        # Verify the restoration by re-reading. Without this, rollback is the same unverified
        # claim the baseline made (defect BASE-004).
        try:
            observed = spec.capture(env=environment, params={})
        except Exception as error:  # noqa: BLE001
            return outcome(
                OperationStatus.ROLLBACK_PARTIAL,
                error_category=_categorise(error),
                detail=f"restore ran but could not be verified: {error}",
                residual_drift=(f"{record.operation_id}: restoration unverified",),
            )

        if not observed.equals(captured):
            differences = captured.differences(observed)
            return outcome(
                OperationStatus.ROLLBACK_PARTIAL,
                error_category="verification_failed",
                detail="restored state does not match the captured state",
                observed_after=observed,
                residual_drift=tuple(f"{record.operation_id}: {d}" for d in differences),
            )

        self.journal.record_phase(
            transaction_id, record.sequence, LifecyclePhase.ROLLBACK_VERIFIED,
            status=OperationStatus.ROLLBACK_SUCCEEDED,
        )
        return outcome(
            OperationStatus.ROLLBACK_SUCCEEDED,
            observed_after=observed,
            verified=True,
            changed=True,
        )

    # -- recovery ----------------------------------------------------------

    def recover(
        self, *, environment: Environment, on_report: Optional[Callable[[ExecutionReport], None]] = None
    ) -> list[ExecutionReport]:
        """Find interrupted transactions and put the machine back.

        Called on startup and by ``winopt recover``. A transaction whose journal shows an operation
        past ``APPLY_STARTED`` is assumed to have touched the machine, even if no result was ever
        recorded -- because the process can die between the mutating call returning and the journal
        write (defect CORE-011).
        """
        reports: list[ExecutionReport] = []
        with ExecutionLock(self.lock_path):
            for record in self.journal.incomplete_transactions():
                report = ExecutionReport(
                    transaction_id=record.transaction_id,
                    plan_id=record.plan_id,
                    state=record.state,
                    detail=f"recovering transaction left in state {record.state.value}",
                )
                self._rollback_transaction(record.transaction_id, environment, report)
                reports.append(report)
                if on_report:
                    on_report(report)
        return reports
