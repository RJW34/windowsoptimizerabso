"""
System information gathering - OS version, hardware, current state
"""

from __future__ import annotations

import os
import platform
import socket
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from loguru import logger

# These imports will work on Windows
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil not available - limited system info")

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

try:
    import wmi
    HAS_WMI = True
except ImportError:
    HAS_WMI = False


@dataclass
class CPUInfo:
    """CPU information"""
    name: str
    cores_physical: int
    cores_logical: int
    frequency_mhz: float
    usage_percent: float
    architecture: str


@dataclass
class MemoryInfo:
    """Memory information"""
    total_gb: float
    available_gb: float
    used_gb: float
    percent_used: float


@dataclass
class DiskInfo:
    """Disk information"""
    device: str
    mountpoint: str
    filesystem: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent_used: float


@dataclass
class NetworkInfo:
    """Network adapter information"""
    name: str
    mac_address: str
    ipv4_addresses: list[str]
    ipv6_addresses: list[str]
    is_up: bool
    speed_mbps: int


@dataclass
class WindowsInfo:
    """Windows-specific information"""
    edition: str
    version: str
    build: str
    product_name: str
    registered_owner: str
    install_date: Optional[datetime]
    last_boot: Optional[datetime]
    uptime: Optional[timedelta]


@dataclass
class SystemInfo:
    """
    Complete system information aggregator.
    Gathers all relevant system data for optimization decisions.
    """

    hostname: str = ""
    platform: str = ""
    python_version: str = ""
    cpu: Optional[CPUInfo] = None
    memory: Optional[MemoryInfo] = None
    disks: list[DiskInfo] = field(default_factory=list)
    networks: list[NetworkInfo] = field(default_factory=list)
    windows: Optional[WindowsInfo] = None
    is_admin: bool = False
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def gather(cls) -> SystemInfo:
        """Gather all system information"""
        info = cls()
        info.hostname = socket.gethostname()
        info.platform = platform.system()
        info.python_version = platform.python_version()
        info.is_admin = cls._check_admin()
        info.timestamp = datetime.now()

        # Gather component info
        info.cpu = cls._get_cpu_info()
        info.memory = cls._get_memory_info()
        info.disks = cls._get_disk_info()
        info.networks = cls._get_network_info()

        if info.platform == "Windows":
            info.windows = cls._get_windows_info()

        return info

    @staticmethod
    def _check_admin() -> bool:
        """Check if running with admin privileges"""
        try:
            if platform.system() == "Windows":
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            else:
                return os.geteuid() == 0
        except Exception:
            return False

    @staticmethod
    def _get_cpu_info() -> Optional[CPUInfo]:
        """Get CPU information"""
        if not HAS_PSUTIL:
            return None

        try:
            freq = psutil.cpu_freq()
            return CPUInfo(
                name=platform.processor() or "Unknown",
                cores_physical=psutil.cpu_count(logical=False) or 0,
                cores_logical=psutil.cpu_count(logical=True) or 0,
                frequency_mhz=freq.current if freq else 0,
                usage_percent=psutil.cpu_percent(interval=0.1),
                architecture=platform.machine(),
            )
        except Exception as e:
            logger.error(f"Error getting CPU info: {e}")
            return None

    @staticmethod
    def _get_memory_info() -> Optional[MemoryInfo]:
        """Get memory information"""
        if not HAS_PSUTIL:
            return None

        try:
            mem = psutil.virtual_memory()
            return MemoryInfo(
                total_gb=mem.total / (1024**3),
                available_gb=mem.available / (1024**3),
                used_gb=mem.used / (1024**3),
                percent_used=mem.percent,
            )
        except Exception as e:
            logger.error(f"Error getting memory info: {e}")
            return None

    @staticmethod
    def _get_disk_info() -> list[DiskInfo]:
        """Get disk information"""
        if not HAS_PSUTIL:
            return []

        disks = []
        try:
            for partition in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disks.append(DiskInfo(
                        device=partition.device,
                        mountpoint=partition.mountpoint,
                        filesystem=partition.fstype,
                        total_gb=usage.total / (1024**3),
                        used_gb=usage.used / (1024**3),
                        free_gb=usage.free / (1024**3),
                        percent_used=usage.percent,
                    ))
                except PermissionError:
                    continue
        except Exception as e:
            logger.error(f"Error getting disk info: {e}")

        return disks

    @staticmethod
    def _get_network_info() -> list[NetworkInfo]:
        """Get network adapter information"""
        if not HAS_PSUTIL:
            return []

        networks = []
        try:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()

            for name, addresses in addrs.items():
                ipv4 = []
                ipv6 = []
                mac = ""

                for addr in addresses:
                    if addr.family.name == "AF_INET":
                        ipv4.append(addr.address)
                    elif addr.family.name == "AF_INET6":
                        ipv6.append(addr.address)
                    elif addr.family.name == "AF_LINK":
                        mac = addr.address

                stat = stats.get(name)
                networks.append(NetworkInfo(
                    name=name,
                    mac_address=mac,
                    ipv4_addresses=ipv4,
                    ipv6_addresses=ipv6,
                    is_up=stat.isup if stat else False,
                    speed_mbps=stat.speed if stat else 0,
                ))
        except Exception as e:
            logger.error(f"Error getting network info: {e}")

        return networks

    @staticmethod
    def _get_windows_info() -> Optional[WindowsInfo]:
        """Get Windows-specific information"""
        if not HAS_WINREG:
            return None

        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
            ) as key:
                def get_value(name: str, default: str = "") -> str:
                    try:
                        return str(winreg.QueryValueEx(key, name)[0])
                    except FileNotFoundError:
                        return default

                edition = get_value("EditionID")
                version = get_value("DisplayVersion") or get_value("ReleaseId")
                build = get_value("CurrentBuild")
                product = get_value("ProductName")
                owner = get_value("RegisteredOwner")

                # Install date (Unix timestamp)
                install_date = None
                try:
                    install_ts = winreg.QueryValueEx(key, "InstallDate")[0]
                    install_date = datetime.fromtimestamp(install_ts)
                except (FileNotFoundError, ValueError):
                    pass

            # Boot time from psutil
            last_boot = None
            uptime = None
            if HAS_PSUTIL:
                try:
                    boot_time = psutil.boot_time()
                    last_boot = datetime.fromtimestamp(boot_time)
                    uptime = datetime.now() - last_boot
                except Exception:
                    pass

            return WindowsInfo(
                edition=edition,
                version=version,
                build=build,
                product_name=product,
                registered_owner=owner,
                install_date=install_date,
                last_boot=last_boot,
                uptime=uptime,
            )
        except Exception as e:
            logger.error(f"Error getting Windows info: {e}")
            return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "hostname": self.hostname,
            "platform": self.platform,
            "python_version": self.python_version,
            "is_admin": self.is_admin,
            "timestamp": self.timestamp.isoformat(),
            "cpu": {
                "name": self.cpu.name,
                "cores_physical": self.cpu.cores_physical,
                "cores_logical": self.cpu.cores_logical,
                "frequency_mhz": self.cpu.frequency_mhz,
                "usage_percent": self.cpu.usage_percent,
                "architecture": self.cpu.architecture,
            } if self.cpu else None,
            "memory": {
                "total_gb": round(self.memory.total_gb, 2),
                "available_gb": round(self.memory.available_gb, 2),
                "used_gb": round(self.memory.used_gb, 2),
                "percent_used": round(self.memory.percent_used, 1),
            } if self.memory else None,
            "disks": [
                {
                    "device": d.device,
                    "mountpoint": d.mountpoint,
                    "filesystem": d.filesystem,
                    "total_gb": round(d.total_gb, 2),
                    "free_gb": round(d.free_gb, 2),
                    "percent_used": round(d.percent_used, 1),
                }
                for d in self.disks
            ],
            "windows": {
                "edition": self.windows.edition,
                "version": self.windows.version,
                "build": self.windows.build,
                "product_name": self.windows.product_name,
                "uptime_hours": round(
                    self.windows.uptime.total_seconds() / 3600, 1
                ) if self.windows.uptime else None,
            } if self.windows else None,
        }

    def get_recommendations(self) -> list[dict[str, str]]:
        """Generate optimization recommendations based on system state"""
        recommendations = []

        # Memory recommendations
        if self.memory and self.memory.percent_used > 80:
            recommendations.append({
                "category": "memory",
                "priority": "high",
                "message": f"Memory usage is {self.memory.percent_used:.0f}%. Consider closing unused applications or optimizing startup programs.",
            })

        # Disk recommendations
        for disk in self.disks:
            if disk.percent_used > 90:
                recommendations.append({
                    "category": "disk",
                    "priority": "high",
                    "message": f"Disk {disk.mountpoint} is {disk.percent_used:.0f}% full. Run disk cleanup.",
                })
            elif disk.percent_used > 75:
                recommendations.append({
                    "category": "disk",
                    "priority": "medium",
                    "message": f"Disk {disk.mountpoint} is {disk.percent_used:.0f}% full. Consider cleanup.",
                })

        # Uptime recommendation
        if self.windows and self.windows.uptime:
            days = self.windows.uptime.days
            if days > 14:
                recommendations.append({
                    "category": "system",
                    "priority": "low",
                    "message": f"System has been running for {days} days. A restart may improve performance.",
                })

        # Admin recommendation
        if not self.is_admin:
            recommendations.append({
                "category": "permissions",
                "priority": "medium",
                "message": "Not running as administrator. Some optimizations will be unavailable.",
            })

        return recommendations


def quick_info() -> dict[str, Any]:
    """Get quick system summary without full scan"""
    info = {}

    if HAS_PSUTIL:
        info["cpu_percent"] = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        info["memory_percent"] = mem.percent
        info["memory_available_gb"] = round(mem.available / (1024**3), 1)

    info["platform"] = platform.system()
    info["hostname"] = socket.gethostname()

    return info
