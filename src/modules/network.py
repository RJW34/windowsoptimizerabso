"""
Network optimization module
"""

from __future__ import annotations

from typing import Any, Optional

from loguru import logger

from ..safety import guard_mutation, guarded_run

from ..core.engine import (
    OptimizationCategory,
    OptimizationLevel,
    OptimizationResult,
    OptimizationTask,
)
from ..core.registry import RegistryManager, RegistryPaths, RegistryTweaks, RegistryValueType


class NetworkModule:
    """
    Network optimization for better performance.

    Features:
    - TCP/IP stack optimization
    - Nagle algorithm control
    - DNS optimization
    - Network adapter tuning
    - Bandwidth throttling removal
    - QoS optimization
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.registry = RegistryManager()

    def get_tasks(self) -> list[OptimizationTask]:
        """Get network optimization tasks"""
        return [
            OptimizationTask(
                name="optimize_tcp_stack",
                description="Optimize TCP/IP stack settings",
                category=OptimizationCategory.NETWORK,
                level=OptimizationLevel.SAFE,
                execute=self.optimize_tcp_stack,
                rollback=self._rollback_registry,
                requires_admin=True,
            ),
            OptimizationTask(
                name="disable_nagle",
                description="Disable Nagle algorithm for lower latency",
                category=OptimizationCategory.NETWORK,
                level=OptimizationLevel.MODERATE,
                execute=self.disable_nagle,
                rollback=self._rollback_registry,
                requires_admin=True,
            ),
            OptimizationTask(
                name="optimize_dns",
                description="Optimize DNS settings and flush cache",
                category=OptimizationCategory.NETWORK,
                level=OptimizationLevel.SAFE,
                execute=self.optimize_dns,
                requires_admin=True,
            ),
            OptimizationTask(
                name="remove_bandwidth_throttling",
                description="Remove network bandwidth throttling",
                category=OptimizationCategory.NETWORK,
                level=OptimizationLevel.MODERATE,
                execute=self.remove_bandwidth_throttling,
                rollback=self._rollback_registry,
                requires_admin=True,
            ),
            OptimizationTask(
                name="optimize_network_adapters",
                description="Optimize network adapter settings",
                category=OptimizationCategory.NETWORK,
                level=OptimizationLevel.MODERATE,
                execute=self.optimize_adapters,
                requires_admin=True,
            ),
            OptimizationTask(
                name="disable_network_throttling",
                description="Disable network throttling for multimedia",
                category=OptimizationCategory.NETWORK,
                level=OptimizationLevel.SAFE,
                execute=self.disable_multimedia_throttling,
                rollback=self._rollback_registry,
                requires_admin=True,
            ),
        ]

    def _set_registry_values(
        self, tweaks: list[tuple[str, str, Any, RegistryValueType]], operation: str
    ) -> OptimizationResult:
        """Apply registry tweaks"""
        success_count = 0
        fail_count = 0
        rollback_data = []

        for path, name, value, value_type in tweaks:
            original = self.registry.get_value(path, name)
            rollback_data.append({
                "path": path,
                "name": name,
                "original": original,
                "type": value_type.name,
            })

            if self.dry_run:
                success_count += 1
                continue

            if self.registry.set_value(path, name, value, value_type):
                success_count += 1
            else:
                fail_count += 1

        return OptimizationResult(
            success=fail_count == 0,
            module="network",
            operation=operation,
            message=f"Applied {success_count}/{success_count + fail_count} settings",
            rollback_data={"registry": rollback_data},
        )

    def _rollback_registry(self, data: dict) -> bool:
        """Rollback registry changes"""
        if "registry" not in data:
            return False

        for entry in data["registry"]:
            path = entry["path"]
            name = entry["name"]
            original = entry["original"]

            if original is None:
                self.registry.delete_value(path, name)
            else:
                value_type = RegistryValueType[entry["type"]]
                self.registry.set_value(path, name, original, value_type)

        return True

    def optimize_tcp_stack(self) -> OptimizationResult:
        """Optimize TCP/IP stack for better performance"""
        tweaks = [
            # Enable TCP auto-tuning
            (RegistryPaths.TCP_IP, "EnableWsd", 0, RegistryValueType.DWORD),
            # Increase TCP window size
            (RegistryPaths.TCP_IP, "Tcp1323Opts", 1, RegistryValueType.DWORD),
            # Enable TCP timestamps
            (RegistryPaths.TCP_IP, "TcpTimedWaitDelay", 30, RegistryValueType.DWORD),
            # Reduce time wait
            (RegistryPaths.TCP_IP, "MaxUserPort", 65534, RegistryValueType.DWORD),
            # Increase ephemeral port range
            (RegistryPaths.TCP_IP, "TcpNumConnections", 0x00fffffe, RegistryValueType.DWORD),
            # Enable connection keep-alive
            (RegistryPaths.TCP_IP, "KeepAliveTime", 300000, RegistryValueType.DWORD),
            (RegistryPaths.TCP_IP, "KeepAliveInterval", 1000, RegistryValueType.DWORD),
        ]

        return self._set_registry_values(tweaks, "optimize_tcp_stack")

    def disable_nagle(self) -> OptimizationResult:
        """
        Disable Nagle algorithm for lower latency.

        Nagle bundles small packets which can cause latency in games and real-time apps.
        """
        # Find network adapter GUIDs
        adapters_path = r"HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
        subkeys = self.registry.enumerate_subkeys(adapters_path)

        tweaks = []
        for adapter_guid in subkeys:
            adapter_path = f"{adapters_path}\\{adapter_guid}"
            # Only modify adapters that have an IP address (active adapters)
            ip = self.registry.get_value(adapter_path, "IPAddress")
            dhcp = self.registry.get_value(adapter_path, "DhcpIPAddress")

            if ip or dhcp:
                tweaks.append((adapter_path, "TcpAckFrequency", 1, RegistryValueType.DWORD))
                tweaks.append((adapter_path, "TCPNoDelay", 1, RegistryValueType.DWORD))

        if not tweaks:
            return OptimizationResult(
                success=True,
                module="network",
                operation="disable_nagle",
                message="No active network adapters found",
            )

        return self._set_registry_values(tweaks, "disable_nagle")

    def optimize_dns(self) -> OptimizationResult:
        """Optimize DNS settings and flush cache"""
        # Registry tweaks for DNS
        tweaks = [
            # Increase DNS cache size
            (r"HKLM\SYSTEM\CurrentControlSet\Services\Dnscache\Parameters", "MaxCacheEntryTtlLimit", 86400, RegistryValueType.DWORD),
            (r"HKLM\SYSTEM\CurrentControlSet\Services\Dnscache\Parameters", "MaxCacheTtl", 86400, RegistryValueType.DWORD),
            # Enable negative cache
            (r"HKLM\SYSTEM\CurrentControlSet\Services\Dnscache\Parameters", "NegativeCacheTime", 300, RegistryValueType.DWORD),
        ]

        result = self._set_registry_values(tweaks, "optimize_dns")

        # Flush DNS cache
        if not self.dry_run:
            try:
                guarded_run(["ipconfig", "/flushdns"], timeout=10)
                guarded_run(["ipconfig", "/registerdns"], timeout=10)
            except Exception as e:
                logger.warning(f"Error flushing DNS: {e}")

        return result

    def remove_bandwidth_throttling(self) -> OptimizationResult:
        """Remove network bandwidth throttling"""
        tweaks = RegistryTweaks.optimize_network()

        # Additional throttling tweaks
        tweaks.extend([
            # Disable bandwidth limit
            (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\Psched", "NonBestEffortLimit", 0, RegistryValueType.DWORD),
            # Disable auto-tuning level restriction
            (RegistryPaths.TCP_IP, "EnableTCPA", 1, RegistryValueType.DWORD),
        ])

        return self._set_registry_values(tweaks, "remove_bandwidth_throttling")

    def optimize_adapters(self) -> OptimizationResult:
        """Optimize network adapter settings using netsh"""
        commands = [
            # Set TCP auto-tuning to normal
            ["netsh", "int", "tcp", "set", "global", "autotuninglevel=normal"],
            # Enable RSS (Receive Side Scaling)
            ["netsh", "int", "tcp", "set", "global", "rss=enabled"],
            # Enable TCP chimney offload
            ["netsh", "int", "tcp", "set", "global", "chimney=enabled"],
            # Enable Direct Cache Access
            ["netsh", "int", "tcp", "set", "global", "dca=enabled"],
            # Enable ECN capability
            ["netsh", "int", "tcp", "set", "global", "ecncapability=enabled"],
            # Set congestion provider
            ["netsh", "int", "tcp", "set", "global", "congestionprovider=ctcp"],
        ]

        success = 0
        failed = 0

        for cmd in commands:
            try:
                if self.dry_run:
                    success += 1
                    continue

                result = guarded_run(cmd, timeout=10)
                if result.returncode == 0:
                    success += 1
                else:
                    failed += 1
                    logger.debug(f"Command failed: {' '.join(cmd)} - {result.stderr}")
            except Exception as e:
                failed += 1
                logger.debug(f"Command error: {' '.join(cmd)} - {e}")

        return OptimizationResult(
            success=failed == 0,
            module="network",
            operation="optimize_network_adapters",
            message=f"Applied {success}/{success + failed} network optimizations",
        )

    def disable_multimedia_throttling(self) -> OptimizationResult:
        """Disable network throttling for multimedia applications"""
        tweaks = [
            # Disable multimedia network throttling
            (RegistryPaths.NETWORK_THROTTLING, "NetworkThrottlingIndex", 0xFFFFFFFF, RegistryValueType.DWORD),
            # Set system responsiveness (0 = gaming/multimedia priority)
            (RegistryPaths.NETWORK_THROTTLING, "SystemResponsiveness", 0, RegistryValueType.DWORD),
            # Disable Nagle for games
            (r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "GPU Priority", 8, RegistryValueType.DWORD),
            (r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "Priority", 6, RegistryValueType.DWORD),
            (r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "Scheduling Category", "High", RegistryValueType.STRING),
            (r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "SFIO Priority", "High", RegistryValueType.STRING),
        ]

        return self._set_registry_values(tweaks, "disable_network_throttling")

    def analyze(self) -> dict[str, Any]:
        """Analyze current network configuration"""
        analysis = {
            "tcp_settings": {},
            "dns_settings": {},
            "adapter_settings": [],
            "recommendations": [],
        }

        # Check TCP settings
        tcp_autotune = self.registry.get_value(RegistryPaths.TCP_IP, "Tcp1323Opts")
        analysis["tcp_settings"]["tcp_timestamps"] = tcp_autotune == 1

        throttle = self.registry.get_value(RegistryPaths.NETWORK_THROTTLING, "NetworkThrottlingIndex")
        analysis["tcp_settings"]["throttling_disabled"] = throttle == 0xFFFFFFFF

        # Get network statistics
        try:
            result = guarded_run(
                ["netsh", "int", "tcp", "show", "global"],
                timeout=10,
            )
            if result.returncode == 0:
                analysis["netsh_global"] = result.stdout
        except Exception:
            pass

        # Check DNS configuration
        try:
            result = guarded_run(
                ["ipconfig", "/displaydns"],
                timeout=10,
            )
            if result.returncode == 0:
                cache_entries = result.stdout.count("Record Name")
                analysis["dns_settings"]["cache_entries"] = cache_entries
        except Exception:
            pass

        # Generate recommendations
        if not analysis["tcp_settings"].get("tcp_timestamps"):
            analysis["recommendations"].append("Enable TCP timestamps for better performance")

        if not analysis["tcp_settings"].get("throttling_disabled"):
            analysis["recommendations"].append("Disable network throttling")

        return analysis

    def reset_network_stack(self) -> OptimizationResult:
        """Reset network stack to defaults (use with caution)"""
        commands = [
            ["netsh", "winsock", "reset"],
            ["netsh", "int", "ip", "reset"],
            ["ipconfig", "/flushdns"],
            ["ipconfig", "/release"],
            ["ipconfig", "/renew"],
        ]

        success = 0
        requires_reboot = False

        for cmd in commands:
            try:
                if self.dry_run:
                    success += 1
                    continue

                result = guarded_run(cmd, timeout=30)
                if result.returncode == 0:
                    success += 1
                    if "restart" in result.stdout.lower() or "reboot" in result.stdout.lower():
                        requires_reboot = True
            except Exception as e:
                logger.error(f"Network reset error: {e}")

        return OptimizationResult(
            success=success > 0,
            module="network",
            operation="reset_network_stack",
            message=f"Reset {success}/{len(commands)} network components" + (" (reboot required)" if requires_reboot else ""),
            details={"requires_reboot": requires_reboot},
        )
