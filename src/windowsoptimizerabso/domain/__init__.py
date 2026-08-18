"""Typed domain model: states, operations, plans, and outcomes.

Nothing in this package touches a machine. It defines what a change *is*, precisely enough that an
executor can capture, apply, verify and reverse it, and that a reviewer can see what they are
approving.
"""

from __future__ import annotations

__all__: list[str] = []
