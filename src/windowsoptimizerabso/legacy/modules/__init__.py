"""
Optimization modules for Windows Optimizer
"""

from .cleanup import CleanupModule
from .privacy import PrivacyModule
from .startup import StartupModule
from .network import NetworkModule
from .gaming import GamingModule
from .visual import VisualModule

__all__ = [
    "CleanupModule",
    "PrivacyModule",
    "StartupModule",
    "NetworkModule",
    "GamingModule",
    "VisualModule",
]
