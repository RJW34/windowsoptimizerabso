"""Quarantined baseline code. Not on the supported path.

Everything under this package is the original prototype, moved here verbatim so that its domain
knowledge -- registry paths, service inventories, cleanup targets, startup locations -- survives
while each operation is triaged and ported to the typed, journalled, verifiably reversible core in
``windowsoptimizerabso.domain`` / ``.executor``.

Rules for this tree, per ``docs/remediation/DECISION_LOG.md`` D-003:

- Nothing here is reachable from the CLI.
- Every mutation site is guarded by ``windowsoptimizerabso.safety``, and legacy mutation requires a
  second explicit opt-in on top of the ordinary one.
- Code here is reference material and a differential-test oracle. It is not a fallback, and it must
  not acquire new callers. When an operation is ported, the legacy implementation is deleted in the
  same commit as the port, and the defect register records the disposition.

Importing this package deliberately pulls in nothing: the submodules are imported explicitly by
the tests and porting tools that need them, so that a stray ``import windowsoptimizerabso.legacy``
cannot drag the entire prototype into a supported process.
"""

from __future__ import annotations

__all__: list[str] = []
