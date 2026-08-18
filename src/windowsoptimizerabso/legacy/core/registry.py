"""
Registry management utilities for Windows optimization
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from loguru import logger

from ...safety import guard_mutation, guarded_run

# winreg is only available on Windows
try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False
    # Stub for type hints on non-Windows
    class winreg:  # type: ignore
        HKEY_LOCAL_MACHINE = None
        HKEY_CURRENT_USER = None
        HKEY_CLASSES_ROOT = None
        HKEY_USERS = None
        REG_SZ = 1
        REG_DWORD = 4
        REG_QWORD = 11
        REG_BINARY = 3
        REG_EXPAND_SZ = 2
        REG_MULTI_SZ = 7
        KEY_READ = 0x20019
        KEY_WRITE = 0x20006
        KEY_ALL_ACCESS = 0xF003F


class RegistryHive(Enum):
    """Registry hives"""
    HKLM = "HKEY_LOCAL_MACHINE"
    HKCU = "HKEY_CURRENT_USER"
    HKCR = "HKEY_CLASSES_ROOT"
    HKU = "HKEY_USERS"

    @property
    def handle(self) -> Any:
        """Get winreg handle for this hive"""
        if not HAS_WINREG:
            return None
        mapping = {
            RegistryHive.HKLM: winreg.HKEY_LOCAL_MACHINE,
            RegistryHive.HKCU: winreg.HKEY_CURRENT_USER,
            RegistryHive.HKCR: winreg.HKEY_CLASSES_ROOT,
            RegistryHive.HKU: winreg.HKEY_USERS,
        }
        return mapping.get(self)


class RegistryValueType(Enum):
    """Registry value types"""
    STRING = "REG_SZ"
    DWORD = "REG_DWORD"
    QWORD = "REG_QWORD"
    BINARY = "REG_BINARY"
    EXPAND_SZ = "REG_EXPAND_SZ"
    MULTI_SZ = "REG_MULTI_SZ"

    @property
    def winreg_type(self) -> int:
        """Get winreg constant for this type"""
        if not HAS_WINREG:
            return 0
        mapping = {
            RegistryValueType.STRING: winreg.REG_SZ,
            RegistryValueType.DWORD: winreg.REG_DWORD,
            RegistryValueType.QWORD: winreg.REG_QWORD,
            RegistryValueType.BINARY: winreg.REG_BINARY,
            RegistryValueType.EXPAND_SZ: winreg.REG_EXPAND_SZ,
            RegistryValueType.MULTI_SZ: winreg.REG_MULTI_SZ,
        }
        return mapping.get(self, winreg.REG_SZ)


@dataclass
class RegistryValue:
    """A registry value with its metadata"""
    name: str
    data: Any
    type: RegistryValueType


@dataclass
class RegistryKey:
    """A registry key with its values"""
    path: str
    hive: RegistryHive
    values: list[RegistryValue]
    subkeys: list[str]


class RegistryManager:
    """
    Safe registry management with backup support.

    Features:
    - Read/write registry values
    - Key enumeration
    - Backup before modification
    - Common optimization tweaks
    """

    def __init__(self):
        if not HAS_WINREG:
            logger.warning("winreg not available - registry operations will fail")

    def _parse_path(self, full_path: str) -> tuple[RegistryHive, str]:
        """Parse a full registry path into hive and subpath"""
        parts = full_path.split("\\", 1)
        hive_str = parts[0].upper()
        subpath = parts[1] if len(parts) > 1 else ""

        # Handle short and long forms
        hive_mapping = {
            "HKLM": RegistryHive.HKLM,
            "HKEY_LOCAL_MACHINE": RegistryHive.HKLM,
            "HKCU": RegistryHive.HKCU,
            "HKEY_CURRENT_USER": RegistryHive.HKCU,
            "HKCR": RegistryHive.HKCR,
            "HKEY_CLASSES_ROOT": RegistryHive.HKCR,
            "HKU": RegistryHive.HKU,
            "HKEY_USERS": RegistryHive.HKU,
        }

        hive = hive_mapping.get(hive_str)
        if not hive:
            raise ValueError(f"Unknown registry hive: {hive_str}")

        return hive, subpath

    def key_exists(self, full_path: str) -> bool:
        """Check if a registry key exists"""
        if not HAS_WINREG:
            return False

        try:
            hive, subpath = self._parse_path(full_path)
            with winreg.OpenKey(hive.handle, subpath, 0, winreg.KEY_READ):
                return True
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.error(f"Error checking key {full_path}: {e}")
            return False

    def value_exists(self, full_path: str, value_name: str) -> bool:
        """Check if a registry value exists"""
        if not HAS_WINREG:
            return False

        try:
            hive, subpath = self._parse_path(full_path)
            with winreg.OpenKey(hive.handle, subpath, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, value_name)
                return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def get_value(
        self, full_path: str, value_name: str, default: Any = None
    ) -> Optional[Any]:
        """Get a registry value"""
        if not HAS_WINREG:
            return default

        try:
            hive, subpath = self._parse_path(full_path)
            with winreg.OpenKey(hive.handle, subpath, 0, winreg.KEY_READ) as key:
                data, _ = winreg.QueryValueEx(key, value_name)
                return data
        except FileNotFoundError:
            return default
        except Exception as e:
            logger.error(f"Error reading {full_path}\\{value_name}: {e}")
            return default

    def set_value(
        self,
        full_path: str,
        value_name: str,
        data: Any,
        value_type: RegistryValueType = RegistryValueType.DWORD,
        create_key: bool = True,
    ) -> bool:
        """
        Set a registry value.

        Args:
            full_path: Full registry path
            value_name: Name of the value
            data: Value data
            value_type: Type of value
            create_key: Create key if it doesn't exist

        Returns:
            True if successful
        """
        guard_mutation(f"registry write {full_path}\\{value_name} = {data!r}", legacy=True)

        if not HAS_WINREG:
            logger.error("winreg not available")
            return False

        try:
            hive, subpath = self._parse_path(full_path)

            if create_key:
                key = winreg.CreateKeyEx(
                    hive.handle, subpath, 0, winreg.KEY_WRITE
                )
            else:
                key = winreg.OpenKey(hive.handle, subpath, 0, winreg.KEY_WRITE)

            with key:
                winreg.SetValueEx(key, value_name, 0, value_type.winreg_type, data)
                logger.debug(f"Set {full_path}\\{value_name} = {data}")
                return True

        except PermissionError:
            logger.error(f"Permission denied setting {full_path}\\{value_name}")
            return False
        except Exception as e:
            logger.error(f"Error setting {full_path}\\{value_name}: {e}")
            return False

    def delete_value(self, full_path: str, value_name: str) -> bool:
        """Delete a registry value"""
        guard_mutation(f"registry delete value {full_path}\\{value_name}", legacy=True)

        if not HAS_WINREG:
            return False

        try:
            hive, subpath = self._parse_path(full_path)
            with winreg.OpenKey(hive.handle, subpath, 0, winreg.KEY_WRITE) as key:
                winreg.DeleteValue(key, value_name)
                logger.debug(f"Deleted {full_path}\\{value_name}")
                return True
        except FileNotFoundError:
            return True  # Already gone
        except Exception as e:
            logger.error(f"Error deleting {full_path}\\{value_name}: {e}")
            return False

    def delete_key(self, full_path: str) -> bool:
        """Delete a registry key (must be empty)"""
        guard_mutation(f"registry delete key {full_path}", legacy=True)

        if not HAS_WINREG:
            return False

        try:
            hive, subpath = self._parse_path(full_path)
            parent_path = "\\".join(subpath.split("\\")[:-1])
            key_name = subpath.split("\\")[-1]

            with winreg.OpenKey(hive.handle, parent_path, 0, winreg.KEY_WRITE) as parent:
                winreg.DeleteKey(parent, key_name)
                logger.debug(f"Deleted key {full_path}")
                return True
        except Exception as e:
            logger.error(f"Error deleting key {full_path}: {e}")
            return False

    def enumerate_values(self, full_path: str) -> list[RegistryValue]:
        """Get all values in a registry key"""
        if not HAS_WINREG:
            return []

        values = []
        try:
            hive, subpath = self._parse_path(full_path)
            with winreg.OpenKey(hive.handle, subpath, 0, winreg.KEY_READ) as key:
                i = 0
                while True:
                    try:
                        name, data, reg_type = winreg.EnumValue(key, i)
                        value_type = self._reg_type_to_enum(reg_type)
                        values.append(RegistryValue(name=name, data=data, type=value_type))
                        i += 1
                    except OSError:
                        break
        except Exception as e:
            logger.error(f"Error enumerating {full_path}: {e}")

        return values

    def enumerate_subkeys(self, full_path: str) -> list[str]:
        """Get all subkeys of a registry key"""
        if not HAS_WINREG:
            return []

        subkeys = []
        try:
            hive, subpath = self._parse_path(full_path)
            with winreg.OpenKey(hive.handle, subpath, 0, winreg.KEY_READ) as key:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(key, i)
                        subkeys.append(name)
                        i += 1
                    except OSError:
                        break
        except Exception as e:
            logger.error(f"Error enumerating subkeys of {full_path}: {e}")

        return subkeys

    def _reg_type_to_enum(self, reg_type: int) -> RegistryValueType:
        """Convert winreg type constant to enum"""
        if not HAS_WINREG:
            return RegistryValueType.STRING

        mapping = {
            winreg.REG_SZ: RegistryValueType.STRING,
            winreg.REG_DWORD: RegistryValueType.DWORD,
            winreg.REG_QWORD: RegistryValueType.QWORD,
            winreg.REG_BINARY: RegistryValueType.BINARY,
            winreg.REG_EXPAND_SZ: RegistryValueType.EXPAND_SZ,
            winreg.REG_MULTI_SZ: RegistryValueType.MULTI_SZ,
        }
        return mapping.get(reg_type, RegistryValueType.STRING)

    def export_key(self, full_path: str, output_file: Path) -> bool:
        """Export a registry key to .reg file using reg.exe"""
        try:
            result = guarded_run(
                ["reg", "export", full_path, str(output_file), "/y"],
                timeout=60,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error exporting {full_path}: {e}")
            return False

    def import_key(self, reg_file: Path) -> bool:
        """Import a .reg file using reg.exe"""
        try:
            result = guarded_run(
                ["reg", "import", str(reg_file)],
                timeout=60,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error importing {reg_file}: {e}")
            return False


# Common registry paths for optimizations
class RegistryPaths:
    """Common registry paths used in optimizations"""

    # Privacy/Telemetry
    TELEMETRY = r"HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection"
    ADVERTISING_ID = r"HKCU\Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo"
    CORTANA = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Search"
    FEEDBACK = r"HKCU\Software\Microsoft\Siuf\Rules"

    # Performance
    VISUAL_EFFECTS = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"
    DESKTOP = r"HKCU\Control Panel\Desktop"
    MOUSE = r"HKCU\Control Panel\Mouse"
    PREFETCH = r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters"

    # Gaming
    GAME_DVR = r"HKCU\System\GameConfigStore"
    GAME_BAR = r"HKCU\Software\Microsoft\GameBar"
    GPU_SCHEDULING = r"HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers"

    # Network
    TCP_IP = r"HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
    NETWORK_THROTTLING = r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"

    # Services
    SERVICES = r"HKLM\SYSTEM\CurrentControlSet\Services"

    # Startup
    RUN = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
    RUN_ONCE = r"HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce"
    RUN_MACHINE = r"HKLM\Software\Microsoft\Windows\CurrentVersion\Run"

    # Explorer
    EXPLORER = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer"
    EXPLORER_ADVANCED = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"


# Predefined optimization tweaks
class RegistryTweaks:
    """Predefined registry tweaks for common optimizations"""

    @staticmethod
    def disable_telemetry() -> list[tuple[str, str, Any, RegistryValueType]]:
        """Registry changes to disable telemetry"""
        return [
            (RegistryPaths.TELEMETRY, "AllowTelemetry", 0, RegistryValueType.DWORD),
            (RegistryPaths.TELEMETRY, "MaxTelemetryAllowed", 0, RegistryValueType.DWORD),
            (RegistryPaths.FEEDBACK, "NumberOfSIUFInPeriod", 0, RegistryValueType.DWORD),
        ]

    @staticmethod
    def disable_advertising_id() -> list[tuple[str, str, Any, RegistryValueType]]:
        """Disable advertising ID"""
        return [
            (RegistryPaths.ADVERTISING_ID, "Enabled", 0, RegistryValueType.DWORD),
        ]

    @staticmethod
    def optimize_visual_effects() -> list[tuple[str, str, Any, RegistryValueType]]:
        """Optimize visual effects for performance"""
        return [
            (RegistryPaths.DESKTOP, "UserPreferencesMask", b"\x90\x12\x03\x80\x10\x00\x00\x00", RegistryValueType.BINARY),
            (RegistryPaths.EXPLORER_ADVANCED, "ListviewAlphaSelect", 0, RegistryValueType.DWORD),
            (RegistryPaths.EXPLORER_ADVANCED, "ListviewShadow", 0, RegistryValueType.DWORD),
            (RegistryPaths.EXPLORER_ADVANCED, "TaskbarAnimations", 0, RegistryValueType.DWORD),
        ]

    @staticmethod
    def optimize_gaming() -> list[tuple[str, str, Any, RegistryValueType]]:
        """Gaming optimizations"""
        return [
            (RegistryPaths.GAME_DVR, "GameDVR_Enabled", 0, RegistryValueType.DWORD),
            (RegistryPaths.GAME_BAR, "AllowAutoGameMode", 1, RegistryValueType.DWORD),
            (RegistryPaths.GAME_BAR, "AutoGameModeEnabled", 1, RegistryValueType.DWORD),
            (RegistryPaths.GPU_SCHEDULING, "HwSchMode", 2, RegistryValueType.DWORD),  # Hardware-accelerated GPU scheduling
        ]

    @staticmethod
    def optimize_network() -> list[tuple[str, str, Any, RegistryValueType]]:
        """Network optimizations"""
        return [
            (RegistryPaths.TCP_IP, "TcpAckFrequency", 1, RegistryValueType.DWORD),
            (RegistryPaths.TCP_IP, "TCPNoDelay", 1, RegistryValueType.DWORD),
            (RegistryPaths.NETWORK_THROTTLING, "NetworkThrottlingIndex", 0xFFFFFFFF, RegistryValueType.DWORD),
            (RegistryPaths.NETWORK_THROTTLING, "SystemResponsiveness", 0, RegistryValueType.DWORD),
        ]

    @staticmethod
    def disable_cortana() -> list[tuple[str, str, Any, RegistryValueType]]:
        """Disable Cortana"""
        return [
            (RegistryPaths.CORTANA, "AllowCortana", 0, RegistryValueType.DWORD),
            (RegistryPaths.CORTANA, "CortanaConsent", 0, RegistryValueType.DWORD),
            (RegistryPaths.CORTANA, "BingSearchEnabled", 0, RegistryValueType.DWORD),
        ]
