"""
Windows service management for optimization
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from loguru import logger

from ..safety import guard_mutation, guarded_run


class ServiceStartType(Enum):
    """Windows service start types"""
    AUTOMATIC = "auto"
    AUTOMATIC_DELAYED = "delayed-auto"
    MANUAL = "demand"
    DISABLED = "disabled"
    BOOT = "boot"
    SYSTEM = "system"


class ServiceState(Enum):
    """Windows service states"""
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    PAUSED = "PAUSED"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


@dataclass
class ServiceInfo:
    """Information about a Windows service"""
    name: str
    display_name: str
    state: ServiceState
    start_type: ServiceStartType
    description: str = ""
    dependencies: list[str] = None
    dependents: list[str] = None
    can_disable: bool = True
    optimization_safe: bool = True
    category: str = ""

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.dependents is None:
            self.dependents = []


class ServiceManager:
    """
    Manage Windows services for optimization.

    Features:
    - Query service status and configuration
    - Change service start type
    - Start/stop services
    - Dependency-aware operations
    - Safe optimization recommendations
    """

    # Services safe to disable for most users
    SAFE_TO_DISABLE = {
        # Telemetry/Diagnostics
        "DiagTrack": "Connected User Experiences and Telemetry",
        "dmwappushservice": "WAP Push Message Routing Service",
        "diagnosticshub.standardcollector.service": "Diagnostics Hub Standard Collector",

        # Xbox (if not gaming)
        "XblAuthManager": "Xbox Live Auth Manager",
        "XblGameSave": "Xbox Live Game Save",
        "XboxGipSvc": "Xbox Accessory Management Service",
        "XboxNetApiSvc": "Xbox Live Networking Service",

        # Rarely used
        "MapsBroker": "Downloaded Maps Manager",
        "lfsvc": "Geolocation Service",
        "SharedAccess": "Internet Connection Sharing (ICS)",
        "RemoteRegistry": "Remote Registry",
        "RemoteAccess": "Routing and Remote Access",
        "NetTcpPortSharing": "Net.Tcp Port Sharing Service",
        "PhoneSvc": "Phone Service",
        "RetailDemo": "Retail Demo Service",
        "WMPNetworkSvc": "Windows Media Player Network Sharing",

        # Fax/Print (if not needed)
        "Fax": "Fax",
        "PrintNotify": "Printer Extensions and Notifications",

        # Tablet/Pen (if not needed)
        "TabletInputService": "Touch Keyboard and Handwriting Panel",
        "WbioSrvc": "Windows Biometric Service",

        # Hyper-V (if not used)
        "vmicguestinterface": "Hyper-V Guest Service Interface",
        "vmicheartbeat": "Hyper-V Heartbeat Service",
        "vmickvpexchange": "Hyper-V Data Exchange Service",
        "vmicrdv": "Hyper-V Remote Desktop Virtualization",
        "vmicshutdown": "Hyper-V Guest Shutdown Service",
        "vmictimesync": "Hyper-V Time Synchronization Service",
        "vmicvmsession": "Hyper-V PowerShell Direct Service",
        "vmicvss": "Hyper-V Volume Shadow Copy Requestor",
    }

    # Services that should NEVER be disabled
    NEVER_DISABLE = {
        "RpcSs": "Remote Procedure Call (RPC)",
        "DcomLaunch": "DCOM Server Process Launcher",
        "RpcEptMapper": "RPC Endpoint Mapper",
        "LSM": "Local Session Manager",
        "PlugPlay": "Plug and Play",
        "Power": "Power",
        "ProfSvc": "User Profile Service",
        "Schedule": "Task Scheduler",
        "SENS": "System Event Notification Service",
        "SystemEventsBroker": "System Events Broker",
        "Themes": "Themes",
        "Winmgmt": "Windows Management Instrumentation",
        "wuauserv": "Windows Update",
        "CryptSvc": "Cryptographic Services",
        "EventLog": "Windows Event Log",
        "LanmanServer": "Server",
        "LanmanWorkstation": "Workstation",
        "Netlogon": "Netlogon",
        "nsi": "Network Store Interface Service",
        "Dhcp": "DHCP Client",
        "Dnscache": "DNS Client",
        "BFE": "Base Filtering Engine",
        "mpssvc": "Windows Defender Firewall",
        "WinDefend": "Windows Defender Antivirus Service",
    }

    # Gaming-specific services to keep
    GAMING_REQUIRED = {
        "Audiosrv": "Windows Audio",
        "AudioEndpointBuilder": "Windows Audio Endpoint Builder",
        "BrokerInfrastructure": "Background Tasks Infrastructure Service",
        "CoreMessagingRegistrar": "CoreMessaging",
        "GameInputSvc": "Game Input Service",
    }

    def __init__(self):
        pass

    def get_service(self, name: str) -> Optional[ServiceInfo]:
        """Get information about a specific service"""
        try:
            # Query service config
            qc_result = guarded_run(
                ["sc", "qc", name],
                timeout=10,
            )

            # Query service status
            query_result = guarded_run(
                ["sc", "query", name],
                timeout=10,
            )

            if qc_result.returncode != 0:
                return None

            # Parse outputs
            display_name = ""
            start_type = ServiceStartType.MANUAL
            state = ServiceState.UNKNOWN
            description = ""

            for line in qc_result.stdout.splitlines():
                line = line.strip()
                if line.startswith("DISPLAY_NAME"):
                    display_name = line.split(":", 1)[1].strip()
                elif line.startswith("START_TYPE"):
                    start_type = self._parse_start_type(line)

            for line in query_result.stdout.splitlines():
                line = line.strip()
                if line.startswith("STATE"):
                    state = self._parse_state(line)

            # Check if safe to optimize
            can_disable = name not in self.NEVER_DISABLE
            optimization_safe = name in self.SAFE_TO_DISABLE

            return ServiceInfo(
                name=name,
                display_name=display_name or name,
                state=state,
                start_type=start_type,
                description=description,
                can_disable=can_disable,
                optimization_safe=optimization_safe,
            )

        except Exception as e:
            logger.error(f"Error getting service {name}: {e}")
            return None

    def _parse_start_type(self, line: str) -> ServiceStartType:
        """Parse start type from sc output"""
        line_lower = line.lower()
        if "auto_start" in line_lower or "automatic" in line_lower:
            if "delayed" in line_lower:
                return ServiceStartType.AUTOMATIC_DELAYED
            return ServiceStartType.AUTOMATIC
        elif "demand_start" in line_lower or "manual" in line_lower:
            return ServiceStartType.MANUAL
        elif "disabled" in line_lower:
            return ServiceStartType.DISABLED
        elif "boot_start" in line_lower:
            return ServiceStartType.BOOT
        elif "system_start" in line_lower:
            return ServiceStartType.SYSTEM
        return ServiceStartType.MANUAL

    def _parse_state(self, line: str) -> ServiceState:
        """Parse state from sc output"""
        line_lower = line.lower()
        if "running" in line_lower:
            return ServiceState.RUNNING
        elif "stopped" in line_lower:
            return ServiceState.STOPPED
        elif "paused" in line_lower:
            return ServiceState.PAUSED
        elif "pending" in line_lower:
            return ServiceState.PENDING
        return ServiceState.UNKNOWN

    def list_services(self) -> list[ServiceInfo]:
        """List all services"""
        services = []

        try:
            result = guarded_run(
                ["sc", "query", "state=", "all"],
                timeout=30,
            )

            current_name = None
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("SERVICE_NAME:"):
                    current_name = line.split(":", 1)[1].strip()
                    service = self.get_service(current_name)
                    if service:
                        services.append(service)

        except Exception as e:
            logger.error(f"Error listing services: {e}")

        return services

    def set_start_type(self, name: str, start_type: ServiceStartType) -> bool:
        """
        Change a service's start type.

        Args:
            name: Service name
            start_type: New start type

        Returns:
            True if successful
        """
        # Safety check
        if name in self.NEVER_DISABLE and start_type == ServiceStartType.DISABLED:
            logger.warning(f"Refusing to disable critical service: {name}")
            return False

        try:
            result = guarded_run(
                ["sc", "config", name, "start=", start_type.value],
                timeout=10,
            )

            if result.returncode == 0:
                logger.info(f"Set {name} start type to {start_type.value}")
                return True
            else:
                logger.error(f"Failed to set {name} start type: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error setting {name} start type: {e}")
            return False

    def start_service(self, name: str) -> bool:
        """Start a service"""
        try:
            result = guarded_run(
                ["sc", "start", name],
                timeout=30,
            )

            success = result.returncode == 0 or "already running" in result.stdout.lower()
            if success:
                logger.info(f"Started service: {name}")
            else:
                logger.error(f"Failed to start {name}: {result.stderr}")
            return success

        except Exception as e:
            logger.error(f"Error starting {name}: {e}")
            return False

    def stop_service(self, name: str) -> bool:
        """Stop a service"""
        # Safety check
        if name in self.NEVER_DISABLE:
            logger.warning(f"Refusing to stop critical service: {name}")
            return False

        try:
            result = guarded_run(
                ["sc", "stop", name],
                timeout=30,
            )

            success = result.returncode == 0 or "not started" in result.stdout.lower()
            if success:
                logger.info(f"Stopped service: {name}")
            else:
                logger.error(f"Failed to stop {name}: {result.stderr}")
            return success

        except Exception as e:
            logger.error(f"Error stopping {name}: {e}")
            return False

    def disable_service(self, name: str, stop: bool = True) -> bool:
        """Disable a service (and optionally stop it)"""
        if stop:
            service = self.get_service(name)
            if service and service.state == ServiceState.RUNNING:
                self.stop_service(name)

        return self.set_start_type(name, ServiceStartType.DISABLED)

    def enable_service(self, name: str, start_type: ServiceStartType = ServiceStartType.MANUAL) -> bool:
        """Enable a previously disabled service"""
        return self.set_start_type(name, start_type)

    def get_optimization_candidates(self) -> list[ServiceInfo]:
        """Get services that can be safely optimized (disabled)"""
        candidates = []

        for name, description in self.SAFE_TO_DISABLE.items():
            service = self.get_service(name)
            if service and service.start_type != ServiceStartType.DISABLED:
                service.description = description
                candidates.append(service)

        return candidates

    def apply_profile(self, profile: str) -> dict[str, bool]:
        """
        Apply a service profile.

        Profiles:
        - gaming: Disable non-gaming services, keep audio/input
        - minimal: Disable everything safe
        - workstation: Balanced, keep productivity services
        - default: Re-enable all to default states
        """
        results = {}

        if profile == "gaming":
            # Disable telemetry/bloat, keep gaming essentials
            for name in self.SAFE_TO_DISABLE:
                if name not in self.GAMING_REQUIRED:
                    results[name] = self.disable_service(name)

        elif profile == "minimal":
            # Disable everything safe
            for name in self.SAFE_TO_DISABLE:
                results[name] = self.disable_service(name)

        elif profile == "workstation":
            # Disable telemetry but keep more features
            telemetry_services = ["DiagTrack", "dmwappushservice", "diagnosticshub.standardcollector.service"]
            for name in telemetry_services:
                results[name] = self.disable_service(name)

        elif profile == "default":
            # Re-enable services to manual
            for name in self.SAFE_TO_DISABLE:
                results[name] = self.enable_service(name, ServiceStartType.MANUAL)

        return results

    def get_dependencies(self, name: str) -> list[str]:
        """Get services that this service depends on"""
        try:
            result = guarded_run(
                ["sc", "qc", name],
                timeout=10,
            )

            dependencies = []
            capture = False
            for line in result.stdout.splitlines():
                if "DEPENDENCIES" in line:
                    capture = True
                    # Check if dependency is on same line
                    parts = line.split(":", 1)
                    if len(parts) > 1 and parts[1].strip():
                        dependencies.append(parts[1].strip())
                elif capture and line.strip() and not line.strip().startswith(("SERVICE_NAME", "TYPE", "START", "ERROR", "BINARY", "LOAD", "TAG", "DISPLAY")):
                    dependencies.append(line.strip())
                elif capture and (not line.strip() or line.strip().startswith(("SERVICE_NAME", "TYPE", "START"))):
                    capture = False

            return dependencies

        except Exception as e:
            logger.error(f"Error getting dependencies for {name}: {e}")
            return []

    def get_dependents(self, name: str) -> list[str]:
        """Get services that depend on this service"""
        try:
            result = guarded_run(
                ["sc", "enumdepend", name],
                timeout=10,
            )

            dependents = []
            for line in result.stdout.splitlines():
                if line.strip().startswith("SERVICE_NAME:"):
                    dep_name = line.split(":", 1)[1].strip()
                    dependents.append(dep_name)

            return dependents

        except Exception as e:
            logger.error(f"Error getting dependents for {name}: {e}")
            return []
