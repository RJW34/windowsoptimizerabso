"""Domain enumerations.

Every enum here carries explicit values. The baseline's ``OptimizationLevel`` used ``auto()`` and
then compared risk by ``list(Enum).index(...)``, so the meaning of "safe" depended on the order the
members happened to be declared in, and inserting a member silently re-ranked every task. It also
placed ``CUSTOM`` in that ordering, where it has no defined position at all (defect CORE-017).
"""

from __future__ import annotations

from enum import Enum, IntEnum


class Risk(IntEnum):
    """How much a change can cost the user if it is wrong.

    Ordered by explicit value, so the ordering is a decision rather than a side effect of
    declaration order. There is no ``CUSTOM``: risk is a property of an operation, not a mode.
    """

    #: Cosmetic or fully session-scoped. Reverting restores the exact prior state immediately.
    MINIMAL = 10
    #: Changes behaviour a user may notice, but exactly reversible with no reboot.
    LOW = 20
    #: Exactly reversible, but requires a reboot, logoff, or Explorer restart to take effect.
    MODERATE = 30
    #: Affects a security, capture, accessibility or connectivity feature the user may depend on.
    HIGH = 40
    #: Not exactly reversible. An operation at this level may not be presented as safe to undo.
    IRREVERSIBLE = 50


class Scope(Enum):
    """What a change applies to.

    ``USER`` scope obliges an operation to name the target SID explicitly: an elevated process's
    ``HKEY_CURRENT_USER`` is the *elevating account's* hive, not the interactive user's, so a
    user-scoped write from an elevated executor lands in the wrong place unless it is told
    otherwise (defects PRV-007, VIS-005, CORE-014).
    """

    MACHINE = "machine"
    USER = "user"
    FILE = "file"
    PROCESS = "process"
    SESSION = "session"


class RegistryView(Enum):
    """Which registry view a key is read and written through.

    Implicit views are a rollback hazard: a 32-bit process reading ``HKLM\\SOFTWARE`` is silently
    redirected to ``WOW6432Node``, so capturing in one view and restoring in another restores a
    different key (defect REG-002).
    """

    NATIVE = "native"
    WOW64_32 = "wow64_32"
    WOW64_64 = "wow64_64"


class Presence(Enum):
    """Whether a thing existed at capture time, and if not, how it was missing.

    ``None`` alone may never mean "did not exist". Deleting a value and setting it to an empty
    string are different changes, and rolling them back requires different actions -- one deletes,
    one writes. The baseline stored ``None`` for both.
    """

    #: The containing key/parent does not exist at all.
    CONTAINER_ABSENT = "container_absent"
    #: The container exists but the named item does not.
    ABSENT = "absent"
    #: The item exists and its value was captured.
    PRESENT = "present"


class OperationStatus(Enum):
    """The outcome of one operation.

    A boolean cannot express most of these, which is why the baseline reported skipped, absent,
    dry-run and unverified operations all as success (defects CORE-016, BASE-013).
    """

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"
    REQUIRES_REBOOT = "requires_reboot"
    ROLLBACK_SUCCEEDED = "rollback_succeeded"
    ROLLBACK_PARTIAL = "rollback_partial"
    ROLLBACK_FAILED = "rollback_failed"

    @property
    def is_success(self) -> bool:
        """Whether this status may be reported to the user as a completed change.

        Deliberately narrow. ``REQUIRES_REBOOT`` is excluded: the postcondition has not been
        verified yet, and saying "done" before verification is the class of lie this project exists
        to remove.
        """
        return self in {OperationStatus.SUCCEEDED, OperationStatus.ROLLBACK_SUCCEEDED}

    @property
    def changed_the_machine(self) -> bool:
        """Whether this status implies a mutation was attempted and may have landed.

        Drives rollback: anything that crossed the apply boundary must be considered for
        restoration, including partial and failed operations, because a failure mid-write can still
        have written something.
        """
        return self in {
            OperationStatus.SUCCEEDED,
            OperationStatus.PARTIAL,
            OperationStatus.FAILED,
            OperationStatus.REQUIRES_REBOOT,
        }


class TransactionState(Enum):
    """The state of a whole transaction, as recorded in the journal."""

    PREPARED = "prepared"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    ROLLBACK_PENDING = "rollback_pending"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    ROLLBACK_PARTIAL = "rollback_partial"
    ROLLBACK_FAILED = "rollback_failed"
    REBOOT_PENDING = "reboot_pending"
    RECOVERY_REQUIRED = "recovery_required"

    @property
    def is_terminal(self) -> bool:
        return self in {
            TransactionState.SUCCEEDED,
            TransactionState.ROLLED_BACK,
            TransactionState.FAILED,
        }

    @property
    def needs_recovery(self) -> bool:
        """Whether finding a transaction in this state on startup means work is outstanding.

        A transaction left ``RUNNING`` is the crash case: the process died between the apply call
        and the journal write, so the machine may hold a change nothing has recorded as complete.
        """
        return self in {
            TransactionState.RUNNING,
            TransactionState.ROLLING_BACK,
            TransactionState.ROLLBACK_PENDING,
            TransactionState.RECOVERY_REQUIRED,
            TransactionState.PARTIAL,
        }


class LifecyclePhase(Enum):
    """Journalled transitions for a single operation, in order.

    The ordering matters for recovery: on restart, the last recorded phase says whether the machine
    could have been touched. Anything at or past ``APPLY_STARTED`` must be treated as possibly
    mutated, even if no result was ever written.
    """

    PLANNED = "planned"
    PRESTATE_CAPTURED = "prestate_captured"
    PRESTATE_DURABLE = "prestate_durable"
    APPLY_STARTED = "apply_started"
    APPLY_RETURNED = "apply_returned"
    POSTSTATE_VERIFIED = "poststate_verified"
    COMMITTED = "committed"
    ROLLBACK_STARTED = "rollback_started"
    ROLLBACK_RETURNED = "rollback_returned"
    ROLLBACK_VERIFIED = "rollback_verified"

    @property
    def crossed_apply_boundary(self) -> bool:
        """Whether reaching this phase means a mutating call may have been made."""
        return self in {
            LifecyclePhase.APPLY_STARTED,
            LifecyclePhase.APPLY_RETURNED,
            LifecyclePhase.POSTSTATE_VERIFIED,
            LifecyclePhase.COMMITTED,
            LifecyclePhase.ROLLBACK_STARTED,
            LifecyclePhase.ROLLBACK_RETURNED,
            LifecyclePhase.ROLLBACK_VERIFIED,
        }


class ActivationRequirement(Enum):
    """What has to happen before a change is actually in effect.

    Distinct from "the write succeeded". A registry value can be set correctly and have no effect
    until Explorer restarts, and reporting that as a completed optimisation is misleading
    (defect VIS-006).
    """

    IMMEDIATE = "immediate"
    EXPLORER_RESTART = "explorer_restart"
    LOGOFF = "logoff"
    REBOOT = "reboot"
    SERVICE_RESTART = "service_restart"
