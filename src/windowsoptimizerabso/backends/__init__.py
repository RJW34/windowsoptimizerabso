"""Backend interfaces and implementations.

``protocols`` defines what a backend must do; ``fake`` is the deterministic in-memory machine the
test suite runs against. Windows implementations live under ``windows/`` and are the only place
outside ``safety`` allowed to touch ``winreg`` or a subprocess.
"""

from __future__ import annotations

__all__: list[str] = []
