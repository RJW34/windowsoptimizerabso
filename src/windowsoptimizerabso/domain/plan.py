"""Immutable execution plans.

A plan is the only thing the privileged executor accepts. It carries operation *ids* and validated
parameters -- never scripts, registry paths, service names, or deletion roots -- so approving a plan
approves a bounded, reviewable set of changes rather than a capability.

Three properties make that meaningful:

- **Digest binding.** The digest covers every field that affects what will be done. Editing a plan
  file invalidates it, so the thing that was reviewed is the thing that runs.
- **Freshness.** Plans expire. State observed an hour ago is not evidence about the machine now.
- **Drift detection.** The state captured at planning time is stored in the plan, and apply re-reads
  it. If the machine moved, the plan is refused rather than applied to a machine it no longer
  describes (defects CORE-012, SEC-005).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from . import codecs
from .enums import ActivationRequirement, Risk, Scope
from .operation import Applicability, Environment, OperationRegistry, OperationSpec
from .state import StateSet

#: Bumped when the plan structure changes incompatibly. A plan written by a newer schema is
#: refused rather than partially understood.
PLAN_SCHEMA_VERSION = 1

#: How long a plan may sit between planning and applying. Deliberately short: the whole point of
#: the captured planning state is that it still describes the machine.
DEFAULT_PLAN_LIFETIME = timedelta(minutes=30)


class PlanError(ValueError):
    """Raised when a plan is malformed, expired, forged, or does not match this machine."""


@dataclass(frozen=True)
class PlannedOperation:
    """One operation as it will be executed, with the state observed while planning."""

    operation_id: str
    parameters: dict[str, Any]
    title: str
    explanation: str
    risk: Risk
    scope: Scope
    requires_admin: bool
    activation: ActivationRequirement
    applicability: Applicability
    exactly_reversible: bool
    evidence_source: str
    evidence_summary: str
    tradeoffs: str
    #: State read while planning. Apply re-reads it and refuses if it moved.
    observed_state: StateSet
    #: What this operation intends to make true, in words. Rendered for approval.
    desired_state: str

    def digest_payload(self) -> dict[str, Any]:
        """Everything that must not change between review and execution."""
        return {
            "operation_id": self.operation_id,
            "parameters": self.parameters,
            "risk": int(self.risk),
            "scope": self.scope.value,
            "requires_admin": self.requires_admin,
            "activation": self.activation.value,
            "exactly_reversible": self.exactly_reversible,
            "observed_state_digest": self.observed_state.digest,
            "desired_state": self.desired_state,
        }

    def to_payload(self) -> dict[str, Any]:
        return {
            **self.digest_payload(),
            "title": self.title,
            "explanation": self.explanation,
            "applicable": self.applicability.applicable,
            "applicability_reason": self.applicability.reason,
            "already_satisfied": self.applicability.already_satisfied,
            "evidence_source": self.evidence_source,
            "evidence_summary": self.evidence_summary,
            "tradeoffs": self.tradeoffs,
            "observed_state": codecs.loads(self.observed_state.serialise()),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> PlannedOperation:
        return cls(
            operation_id=payload["operation_id"],
            parameters=payload.get("parameters") or {},
            title=payload.get("title", ""),
            explanation=payload.get("explanation", ""),
            risk=Risk(payload["risk"]),
            scope=Scope(payload["scope"]),
            requires_admin=payload["requires_admin"],
            activation=ActivationRequirement(payload["activation"]),
            applicability=Applicability(
                applicable=payload.get("applicable", True),
                reason=payload.get("applicability_reason", ""),
                already_satisfied=payload.get("already_satisfied", False),
            ),
            exactly_reversible=payload["exactly_reversible"],
            evidence_source=payload.get("evidence_source", ""),
            evidence_summary=payload.get("evidence_summary", ""),
            tradeoffs=payload.get("tradeoffs", ""),
            observed_state=StateSet.deserialise(codecs.dumps(payload["observed_state"])),
            desired_state=payload["desired_state"],
        )


@dataclass(frozen=True)
class ExecutionPlan:
    """An immutable, digest-bound set of changes awaiting approval."""

    plan_id: str
    created_at: datetime
    expires_at: datetime
    #: Redacted machine identity. Applying a plan built for another machine is refused.
    machine_fingerprint: str
    #: The interactive user the plan was built for. User-scoped operations write this SID's hive.
    target_user_sid: Optional[str]
    os_build: Optional[str]
    operations: tuple[PlannedOperation, ...]
    profile_id: Optional[str] = None
    profile_version: Optional[str] = None
    schema_version: int = PLAN_SCHEMA_VERSION
    notes: tuple[str, ...] = field(default_factory=tuple)

    # -- identity ----------------------------------------------------------

    def digest_payload(self) -> dict[str, Any]:
        """The fields the digest covers.

        Explicitly *not* everything: ``notes`` and rendered prose are excluded so that improving an
        explanation does not invalidate an approved plan, while anything that changes what will
        happen to the machine is included.
        """
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "machine_fingerprint": self.machine_fingerprint,
            "target_user_sid": self.target_user_sid,
            "os_build": self.os_build,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "operations": [op.digest_payload() for op in self.operations],
        }

    @property
    def digest(self) -> str:
        return codecs.digest(self.digest_payload())

    @property
    def short_digest(self) -> str:
        """First 12 hex characters: what a human is asked to type back to confirm."""
        return self.digest[:12]

    # -- risk summary ------------------------------------------------------

    @property
    def highest_risk(self) -> Risk:
        return max((op.risk for op in self.applicable_operations), default=Risk.MINIMAL)

    @property
    def applicable_operations(self) -> tuple[PlannedOperation, ...]:
        return tuple(op for op in self.operations if op.applicability.applicable)

    @property
    def operations_to_run(self) -> tuple[PlannedOperation, ...]:
        """Applicable operations that would actually change something.

        An operation whose desired state is already true is kept in the plan -- so the reader can
        see it was considered -- but is not executed. A zero-change plan is a valid outcome.
        """
        return tuple(
            op for op in self.applicable_operations if not op.applicability.already_satisfied
        )

    @property
    def is_zero_change(self) -> bool:
        return not self.operations_to_run

    @property
    def requires_admin(self) -> bool:
        return any(op.requires_admin for op in self.operations_to_run)

    @property
    def activation_requirements(self) -> tuple[ActivationRequirement, ...]:
        return tuple(sorted({op.activation for op in self.operations_to_run}, key=lambda a: a.value))

    @property
    def irreversible_operations(self) -> tuple[PlannedOperation, ...]:
        return tuple(op for op in self.operations_to_run if not op.exactly_reversible)

    # -- validation --------------------------------------------------------

    def is_expired(self, *, now: Optional[datetime] = None) -> bool:
        return (now or datetime.now(timezone.utc)) > self.expires_at

    def validate_for_execution(
        self,
        *,
        registry: OperationRegistry,
        environment: Environment,
        machine_fingerprint: str,
        confirmation_digest: str,
        now: Optional[datetime] = None,
    ) -> None:
        """Every check that must pass before a single mutation is attempted.

        Ordered cheapest-and-most-fundamental first, so a forged or stale plan is rejected before
        anything touches the machine. Raises :class:`PlanError` with a specific reason; it never
        returns a boolean, because a caller that ignores a boolean applies an unvalidated plan.
        """
        if self.schema_version != PLAN_SCHEMA_VERSION:
            raise PlanError(
                f"plan schema version {self.schema_version} cannot be executed by this build "
                f"(expects {PLAN_SCHEMA_VERSION})"
            )

        if confirmation_digest not in {self.digest, self.short_digest}:
            raise PlanError(
                "confirmation digest does not match the plan. Either the plan was edited after it "
                "was reviewed, or the wrong plan was confirmed. Re-plan and review again."
            )

        if self.is_expired(now=now):
            raise PlanError(
                f"plan expired at {self.expires_at.isoformat()}. The state it recorded is no "
                "longer evidence about this machine; re-plan."
            )

        if self.machine_fingerprint != machine_fingerprint:
            raise PlanError(
                "plan was created for a different machine. Plans are not portable: they carry "
                "state captured from one specific machine."
            )

        if self.os_build and environment.os_build and self.os_build != environment.os_build:
            raise PlanError(
                f"plan was created for OS build {self.os_build}, this machine reports "
                f"{environment.os_build}. Applicability must be re-evaluated."
            )

        unknown = [op.operation_id for op in self.operations if op.operation_id not in registry]
        if unknown:
            raise PlanError(
                f"plan references operations that are not registered: {unknown}. A plan cannot "
                "introduce a capability."
            )

        for planned in self.operations_to_run:
            spec: OperationSpec = registry.get(planned.operation_id)
            # Re-validate parameters against the spec rather than trusting the file.
            spec.validate_params(planned.parameters)
            if spec.requires_admin and not environment.is_admin:
                raise PlanError(
                    f"{planned.operation_id} requires administrator rights and this process is not "
                    "elevated"
                )
            if spec.scope is Scope.USER and not environment.target_user_sid:
                raise PlanError(
                    f"{planned.operation_id} is user-scoped but no target user SID was resolved. "
                    "An elevated process's HKCU is the elevating account, not the interactive user."
                )

    # -- serialisation -----------------------------------------------------

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "machine_fingerprint": self.machine_fingerprint,
            "target_user_sid": self.target_user_sid,
            "os_build": self.os_build,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "notes": list(self.notes),
            "operations": [op.to_payload() for op in self.operations],
            "digest": self.digest,
        }

    def serialise(self) -> str:
        return codecs.dumps(self.to_payload())

    @staticmethod
    def deserialise(text: str) -> ExecutionPlan:
        payload = codecs.loads(text)
        if not isinstance(payload, dict):
            raise PlanError("plan file is not an object")
        try:
            plan = ExecutionPlan(
                plan_id=payload["plan_id"],
                created_at=payload["created_at"],
                expires_at=payload["expires_at"],
                machine_fingerprint=payload["machine_fingerprint"],
                target_user_sid=payload.get("target_user_sid"),
                os_build=payload.get("os_build"),
                operations=tuple(PlannedOperation.from_payload(o) for o in payload["operations"]),
                profile_id=payload.get("profile_id"),
                profile_version=payload.get("profile_version"),
                schema_version=payload.get("schema_version", 0),
                notes=tuple(payload.get("notes") or ()),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PlanError(f"malformed plan: {exc}") from exc

        stored = payload.get("digest")
        if stored and stored != plan.digest:
            raise PlanError(
                "plan digest does not match its contents: the file was modified after it was "
                "written. Refusing to load."
            )
        return plan


def new_plan_id() -> str:
    return f"plan-{uuid.uuid4().hex[:12]}"
