"""Turn a selection of operation ids into an immutable, reviewable plan.

The planner is unprivileged and never mutates. It reads current state, decides applicability,
detects conflicts and orders dependencies, then freezes the result and digests it.

An operation that is not applicable stays *in* the plan, marked, rather than being dropped. A
reader needs to see that it was considered and why it will not run -- silently omitting it is how
a tool ends up looking like it did more than it did.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from ..domain.enums import Risk
from ..domain.operation import (
    Applicability,
    Environment,
    OperationError,
    OperationRegistry,
    OperationSpec,
)
from ..domain.plan import (
    DEFAULT_PLAN_LIFETIME,
    ExecutionPlan,
    PlanError,
    PlannedOperation,
    new_plan_id,
)
from ..domain.state import StateSet


class ConflictError(PlanError):
    """Two selected operations touch the same setting, or a dependency is missing."""


class Selection:
    """One operation id plus the parameters a profile supplied for it."""

    def __init__(self, operation_id: str, parameters: dict[str, Any] | None = None) -> None:
        self.operation_id = operation_id
        self.parameters = parameters or {}


def order_by_dependencies(specs: Sequence[OperationSpec]) -> tuple[OperationSpec, ...]:
    """Topologically order operations so dependencies apply first.

    Raises on a cycle rather than picking an arbitrary order: a cycle means the declared
    dependencies are wrong, and guessing would produce a plan whose rollback order is also wrong
    (rollback runs this order reversed).
    """
    by_id = {spec.operation_id: spec for spec in specs}
    ordered: list[OperationSpec] = []
    state: dict[str, str] = {}

    def visit(operation_id: str, trail: tuple[str, ...]) -> None:
        mark = state.get(operation_id)
        if mark == "done":
            return
        if mark == "visiting":
            cycle = " -> ".join([*trail, operation_id])
            raise ConflictError(f"dependency cycle between operations: {cycle}")
        state[operation_id] = "visiting"
        for dependency in by_id[operation_id].depends_on:
            if dependency not in by_id:
                raise ConflictError(
                    f"{operation_id} depends on {dependency}, which is not in this plan"
                )
            visit(dependency, (*trail, operation_id))
        state[operation_id] = "done"
        ordered.append(by_id[operation_id])

    for spec in specs:
        visit(spec.operation_id, ())
    return tuple(ordered)


def detect_conflicts(specs: Sequence[OperationSpec]) -> tuple[str, ...]:
    """Report operations that would fight over the same underlying setting.

    Two operations sharing a conflict key both write the same thing, so whichever runs second wins
    and the first one's rollback would restore a value the second one is relying on. This is
    detected at planning time because at apply time the damage is already interleaved.
    """
    seen: dict[str, str] = {}
    conflicts: list[str] = []
    for spec in specs:
        for key in spec.conflict_keys:
            if key in seen:
                conflicts.append(
                    f"{spec.operation_id} and {seen[key]} both modify {key!r}"
                )
            else:
                seen[key] = spec.operation_id
    return tuple(conflicts)


class Planner:
    """Builds plans. Holds no machine state of its own."""

    def __init__(self, registry: OperationRegistry) -> None:
        self.registry = registry

    def plan(
        self,
        selections: Sequence[Selection],
        *,
        environment: Environment,
        machine_fingerprint: str,
        profile_id: str | None = None,
        profile_version: str | None = None,
        lifetime: timedelta = DEFAULT_PLAN_LIFETIME,
        now: datetime | None = None,
    ) -> ExecutionPlan:
        """Produce an immutable plan for ``selections`` against ``environment``.

        Raises:
            OperationError: an id is not registered, or a parameter is not accepted.
            ConflictError: two operations collide, or dependencies are missing or cyclic.
        """
        created = now or datetime.now(timezone.utc)

        specs = [self.registry.get(s.operation_id) for s in selections]
        parameters = {
            s.operation_id: self.registry.get(s.operation_id).validate_params(s.parameters)
            for s in selections
        }

        conflicts = detect_conflicts(specs)
        if conflicts:
            raise ConflictError("; ".join(conflicts))

        ordered = order_by_dependencies(specs)

        planned: list[PlannedOperation] = []
        for spec in ordered:
            params = parameters[spec.operation_id]
            applicability = self._evaluate(spec, environment, params)
            observed = (
                spec.capture(env=environment, params=params)
                if applicability.applicable
                else StateSet()
            )
            planned.append(
                PlannedOperation(
                    operation_id=spec.operation_id,
                    parameters=params,
                    title=spec.title,
                    explanation=spec.explanation,
                    risk=spec.risk,
                    scope=spec.scope,
                    requires_admin=spec.requires_admin,
                    activation=spec.activation,
                    applicability=applicability,
                    exactly_reversible=spec.is_exactly_reversible,
                    evidence_source=spec.evidence.source,
                    evidence_summary=spec.evidence.summary,
                    tradeoffs=spec.evidence.tradeoffs,
                    observed_state=observed,
                    desired_state=self._describe_desired(spec, params),
                )
            )

        notes = []
        irreversible = [p.operation_id for p in planned if not p.exactly_reversible]
        if irreversible:
            notes.append(
                "Not exactly reversible, and rollback cannot restore them: "
                + ", ".join(irreversible)
            )
        unverified = [
            p.operation_id
            for p in planned
            if p.applicability.applicable and not self.registry.get(p.operation_id).evidence.is_authoritative
        ]
        if unverified:
            notes.append(
                "Evidence is not primary documentation for: " + ", ".join(unverified)
            )

        return ExecutionPlan(
            plan_id=new_plan_id(),
            created_at=created,
            expires_at=created + lifetime,
            machine_fingerprint=machine_fingerprint,
            target_user_sid=environment.target_user_sid,
            os_build=environment.os_build,
            operations=tuple(planned),
            profile_id=profile_id,
            profile_version=profile_version,
            notes=tuple(notes),
        )

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _evaluate(
        spec: OperationSpec, environment: Environment, params: dict[str, Any]
    ) -> Applicability:
        """Decide applicability, converting a backend failure into a stated reason.

        An operation whose applicability check raises is *not applicable* with the reason attached,
        rather than being treated as applicable and failing later during apply -- planning must not
        be able to leave the machine in a worse position than not planning at all.
        """
        if environment.os_system != "Windows":
            return Applicability.no(f"requires Windows, this machine reports {environment.os_system}")
        try:
            return spec.check_applicability(env=environment, params=params)
        except OperationError:
            raise
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any failure means unknown
            return Applicability.no(f"could not determine applicability: {exc}")

    @staticmethod
    def _describe_desired(spec: OperationSpec, params: dict[str, Any]) -> str:
        if params:
            rendered = ", ".join(f"{k}={v!r}" for k, v in sorted(params.items()))
            return f"{spec.title} ({rendered})"
        return spec.title


def summarise_risk(plan: ExecutionPlan) -> str:
    """One line for the approval prompt. No superlatives without a measured number."""
    if plan.is_zero_change:
        return "No changes: every applicable operation is already in the desired state."
    counts: dict[Risk, int] = {}
    for op in plan.operations_to_run:
        counts[op.risk] = counts.get(op.risk, 0) + 1
    parts = [f"{count} {risk.name.lower()}" for risk, count in sorted(counts.items(), reverse=True)]
    return f"{len(plan.operations_to_run)} operation(s) to run: " + ", ".join(parts)
