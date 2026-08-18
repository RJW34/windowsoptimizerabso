"""Make the package importable from a source checkout without installing it.

CI also runs the suite against an installed wheel (``tests/test_packaging.py``); this only covers
the developer running ``pytest`` in a fresh clone.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Test-support modules (conftest_operations) live beside the tests, so make the directory
# importable as well as the package under test.
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))
