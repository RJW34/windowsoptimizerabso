"""Typed operation definitions.

An operation is the only unit of change this tool can make. It is a *definition*, not a closure
over arbitrary work: it declares what it needs, captures its own pre-state, applies one narrow
change, verifies the postcondition, and restores the captured state on rollback.

The constraint that shapes this file: **a profile may not hand an operation an arbitrary registry
path, service name, shell string, or deletion root** (defects REG-004, SEC-003). Profiles select
operation IDs from a registry and supply parameters that the operation itself validates against a
declared schema. Nothing external can widen what an operation touches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from .enums import ActivationRequirement, OperationStatus, Risk, Scope
from .state import StateSet


class OperationError(Exception):
    """Raised when an operation is defined or invoked incorrectly. A bug, not a machine condition."""


@dataclass(frozen=True)
class Applicability:
    """Whether an operation makes sense on this machine, and why not if it does not.

    Distinguishing "not applicable" from "failed" is a correctness requirement, not politeness: the
    baseline counted an absent scheduled task as a failure, which made a clean machine look broken
    (defect PRV-006), and reported no-op runs as successful optimisations.
    """

    applicable: bool
    reason: str = ""
    #: True when the machine is already in the desired state. Applying is a verified no-op.
    already_satisfied: bool = False

    @classmethod
    def yes(cls) -> Applicability:
        return cls(applicable=True)

    @classmethod
    def satisfied(cls, reason: str = "already in the desired state") -> Applicability:
        return cls(applicable=True, reason=reason, already_satisfied=True)

    @classmethod
    def no(cls, reason: str) -> Applicability:
        if not reason:
            raise OperationError("a non-applicable result must say why")
        return cls(applicable=False, reason=reason)


@dataclass(frozen=True)
class Evidence:
    """Why an operation is believed to do what it claims.

    Every retained operation needs one. An operation whose only justification is that a tweak list
    recommended it is quarantined or removed -- that is the disposition rule for the folklore in
    the baseline's gaming, network and visual modules.
    """

    #: Primary documentation URL, or an explicit ``experiment:`` reference to a measured result.
    source: str
    #: ISO date the source was checked. Windows behaviour changes by build; a citation with no
    #: date cannot be re-verified.
    accessed: str
    summary: str
    #: What the user gives up. An operation with no stated tradeoff has usually not been thought
    #: about rather than genuinely having none.
    tradeoffs: str = ""
    measured_effect: Optional[str] = None

    @property
    def is_authoritative(self) -> bool:
        """Whether the source is primary documentation rather than a hypothesis.

        Blogs, forums and tweak compilations may generate hypotheses; they do not settle them.
        """
        return self.source.startswith(("https://learn.microsoft.com", "https://docs.microsoft.com",
                                       "https://support.microsoft.com", "experiment:"))


@dataclass(frozen=True)
class Environment:
    """The machine facts an operation needs in order to decide applicability.

    Passed in rather than gathered, so the planner is testable against a fake machine and so that
    plan and apply see the same declared inputs.
    """

    os_system: str = "Windows"
    os_build: Optional[str] = None
    os_edition: Optional[str] = None
    is_admin: bool = False
    #: SID of the interactive user, which is not necessarily the elevated account.
    target_user_sid: Optional[str] = None
    gpu_vendors: tuple[str, ...] = ()
    facts: dict[str, Any] = field(default_factory=dict)


class CaptureFn(Protocol):
    def __call__(self, env: Environment, params: dict[str, Any]) -> StateSet: ...


class ApplyFn(Protocol):
    def __call__(self, env: Environment, params: dict[str, Any], captured: StateSet) -> None: ...


class RestoreFn(Protocol):
    def __call__(self, env: Environment, params: dict[str, Any], captured: StateSet) -> None: ...


class ApplicabilityFn(Protocol):
    def __call__(self, env: Environment, params: dict[str, Any]) -> Applicability: ...


@dataclass(frozen=True)
class OperationSpec:
    """One typed, reversible capability.

    Rollback is not optional. An operation whose captured state cannot be written back is not
    reversible, and must be declared :attr:`Risk.IRREVERSIBLE` so the planner can refuse to bundle
    it with reversible work and the plan can say so in plain words.
    """

    operation_id: str
    title: str
    #: What this changes, in a sentence a user can evaluate. Not marketing: "maximum performance"
    #: without a measured number is banned by the CLI contract.
    explanation: str
    category: str
    risk: Risk
    scope: Scope
    evidence: Evidence

    capture: CaptureFn
    apply: ApplyFn
    restore: RestoreFn
    check_applicability: ApplicabilityFn

    schema_version: int = 1
    requires_admin: bool = True
    activation: ActivationRequirement = ActivationRequirement.IMMEDIATE
    #: Operations sharing a conflict key touch the same underlying setting and may not appear in
    #: one plan together (defect CORE-006).
    conflict_keys: tuple[str, ...] = ()
    #: Operation IDs that must be applied before this one.
    depends_on: tuple[str, ...] = ()
    #: Parameter names this operation accepts, with a validator each. A parameter that is not
    #: declared is rejected; this is what stops a profile widening an operation's blast radius.
    parameters: dict[str, Callable[[Any], bool]] = field(default_factory=dict)
    #: Session-scoped operations are reverted when the target application exits.
    session_scoped: bool = False

    def __post_init__(self) -> None:
        if not self.operation_id or " " in self.operation_id:
            raise OperationError(f"invalid operation id: {self.operation_id!r}")
        if not self.evidence.summary:
            raise OperationError(f"{self.operation_id} has no evidence summary")
        if self.risk >= Risk.HIGH and not self.evidence.tradeoffs:
            raise OperationError(
                f"{self.operation_id} is {self.risk.name} risk and must state its tradeoffs"
            )

    def validate_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Reject anything the operation did not declare.

        Unknown keys are an error rather than being ignored: a profile that sets ``path`` on an
        operation with no ``path`` parameter is either a typo or an attempt to widen the operation,
        and silently dropping it hides both.
        """
        unknown = set(params) - set(self.parameters)
        if unknown:
            raise OperationError(
                f"{self.operation_id} does not accept parameter(s): {sorted(unknown)}"
            )
        for name, validator in self.parameters.items():
            if name in params and not validator(params[name]):
                raise OperationError(f"{self.operation_id}: invalid value for {name!r}")
        return dict(params)

    @property
    def is_exactly_reversible(self) -> bool:
        return self.risk is not Risk.IRREVERSIBLE


class OperationRegistry:
    """The allowlist. The executor will not run an operation that is not in here.

    This is the agent/profile boundary from ``04_SECURITY_AND_AGENT_BOUNDARIES.md``: a plan carries
    operation *ids*, and ids resolve only through this registry, so neither a profile author nor
    anything driving the CLI can introduce a new capability by writing a plan file.
    """

    def __init__(self) -> None:
        self._specs: dict[str, OperationSpec] = {}

    def register(self, spec: OperationSpec) -> OperationSpec:
        if spec.operation_id in self._specs:
            raise OperationError(f"duplicate operation id: {spec.operation_id}")
        self._specs[spec.operation_id] = spec
        return spec

    def get(self, operation_id: str) -> OperationSpec:
        try:
            return self._specs[operation_id]
        except KeyError:
            raise OperationError(
                f"unknown operation {operation_id!r}. Operations must be registered in code; a "
                "plan or profile cannot introduce one."
            ) from None

    def __contains__(self, operation_id: object) -> bool:
        return operation_id in self._specs

    def __len__(self) -> int:
        return len(self._specs)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))


@dataclass(frozen=True)
class Outcome:
    """What actually happened to one operation.

    Replaces the baseline's ``(success: bool, message: str)``, which could not distinguish a
    skipped operation from a completed one, could not say whether the machine changed, and had no
    room for the observed states that make a rollback provable (defects CORE-016, CORE-010).
    """

    operation_id: str
    status: OperationStatus
    started_at: Any
    finished_at: Any
    applicability: Applicability
    changed: bool = False
    observed_before: Optional[StateSet] = None
    observed_after: Optional[StateSet] = None
    verified: bool = False
    activation: ActivationRequirement = ActivationRequirement.IMMEDIATE
    #: Structured category, e.g. "permission_denied", "timeout", "not_found". Not a free string:
    #: callers branch on it.
    error_category: Optional[str] = None
    #: Sanitised, causal detail. Never raw registry data or user paths beyond what was planned.
    detail: str = ""
    #: What rollback could not restore, if anything.
    residual_drift: tuple[str, ...] = ()

    @property
    def rollback_available(self) -> bool:
        return self.observed_before is not None and self.status.changed_the_machine

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "status": self.status.value,
            "changed": self.changed,
            "verified": self.verified,
            "applicable": self.applicability.applicable,
            "applicability_reason": self.applicability.reason,
            "activation": self.activation.value,
            "error_category": self.error_category,
            "detail": self.detail,
            "residual_drift": list(self.residual_drift),
            "rollback_available": self.rollback_available,
        }
