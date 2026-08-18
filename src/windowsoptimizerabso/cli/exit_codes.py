"""Stable process exit codes.

Semantics follow ``docs/remediation/05_CLI_AND_PRODUCT_CONTRACT.md``. The numbers are part of the
public contract: automation depends on them, so they are tested in ``tests/test_cli.py`` and may
only change in a documented breaking release.

The central rule (defect BASE-013): a command may not exit 0 unless it did what it said it did. A
skipped operation, a not-applicable operation, an unverified state and a partial apply each get
their own code, because collapsing them into "success" is how the baseline came to report a
rollback that never happened.
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Process exit codes. See the module docstring for the governing rule."""

    #: Completed, and the postcondition was verified. Also used for a verified no-op.
    SUCCESS = 0

    #: Reserved: Click/Typer uses 1 for unhandled internal errors.
    ERROR = 1

    #: Bad arguments, bad input file, or schema validation failure.
    USAGE = 2

    #: The platform, OS build, or hardware does not support what was asked.
    UNSUPPORTED = 3

    #: Missing administrator rights, or the intended target user could not be resolved.
    PRIVILEGE = 4

    #: The machine state changed since the plan was created. Re-plan required.
    DRIFT = 5

    #: Apply failed before any mutation was attempted. The machine is unchanged.
    APPLY_FAILED = 6

    #: Some operations applied, or a postcondition could not be verified. State is uncertain.
    PARTIAL = 7

    #: A mutation landed and must be rolled back before the machine is left alone.
    ROLLBACK_REQUIRED = 8

    #: Rollback ran but did not fully restore the captured state. Residual drift is reported.
    ROLLBACK_FAILED = 9

    #: An incomplete transaction was found. ``winopt recover`` must run before anything else.
    RECOVERY_REQUIRED = 10

    #: A reboot or logoff is required before the result can be verified.
    REBOOT_REQUIRED = 11

    #: An internal invariant was violated. This is a bug, not a machine condition.
    INTERNAL = 12

    #: Refused: the command would mutate the host while the repository is contained (gate G0).
    CONTAINED = 13


#: One-line descriptions, used by ``winopt doctor`` and by the docs test that keeps the CLI
#: contract document in sync with this enum.
DESCRIPTIONS: dict[ExitCode, str] = {
    ExitCode.SUCCESS: "success, or verified no-op",
    ExitCode.ERROR: "unhandled internal error",
    ExitCode.USAGE: "usage, input, or schema error",
    ExitCode.UNSUPPORTED: "unsupported platform or capability",
    ExitCode.PRIVILEGE: "privilege or target-user error",
    ExitCode.DRIFT: "stale plan, machine state drifted",
    ExitCode.APPLY_FAILED: "apply failed before any mutation",
    ExitCode.PARTIAL: "partial apply or verification failure",
    ExitCode.ROLLBACK_REQUIRED: "rollback required",
    ExitCode.ROLLBACK_FAILED: "rollback partial or failed",
    ExitCode.RECOVERY_REQUIRED: "incomplete transaction, recovery required",
    ExitCode.REBOOT_REQUIRED: "reboot or logoff required before verification",
    ExitCode.INTERNAL: "internal invariant failure",
    ExitCode.CONTAINED: "refused: mutation disabled during remediation",
}
