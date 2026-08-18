"""Windows Optimizer Absolute.

A per-game Windows state planner. Inspection and planning are unprivileged and read-only; any
change to a machine goes through an immutable plan, a durable transaction journal, exact pre-state
capture, and verified rollback.

The project is pre-alpha and under remediation: see ``docs/remediation/`` for the defect register,
the implementation sequence, and which acceptance gates are still open. Importing this package has
no side effects and cannot change a machine.
"""

from __future__ import annotations

#: Pre-release. The version deliberately does not imply maturity while blocking gates are open
#: (defect PKG-005); the baseline claimed 1.0.0 for a tree with no tests, no CI and no rollback.
__version__ = "0.0.1a1"

__all__ = ["__version__"]
