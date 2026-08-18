"""
Privacy and telemetry control module
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from loguru import logger

from ...safety import guard_mutation, guarded_run

from ..core.engine import (
    OptimizationCategory,
    OptimizationLevel,
    OptimizationResult,
    OptimizationTask,
)
from ..core.registry import RegistryManager, RegistryPaths, RegistryTweaks, RegistryValueType


class PrivacyModule:
    """
    Privacy and telemetry control.

    Features:
    - Disable Windows telemetry
    - Block telemetry hosts
    - Disable advertising ID
    - Control Cortana
    - Manage diagnostic data
    - Disable activity history
    - Control location services
    - Manage app permissions
    """

    # Telemetry-related scheduled tasks
    TELEMETRY_TASKS = [
        r"\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser",
        r"\Microsoft\Windows\Application Experience\ProgramDataUpdater",
        r"\Microsoft\Windows\Autochk\Proxy",
        r"\Microsoft\Windows\Customer Experience Improvement Program\Consolidator",
        r"\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip",
        r"\Microsoft\Windows\DiskDiagnostic\Microsoft-Windows-DiskDiagnosticDataCollector",
        r"\Microsoft\Windows\Feedback\Siuf\DmClient",
        r"\Microsoft\Windows\Feedback\Siuf\DmClientOnScenarioDownload",
        r"\Microsoft\Windows\Windows Error Reporting\QueueReporting",
        r"\Microsoft\Windows\CloudExperienceHost\CreateObjectTask",
    ]

    # Known Microsoft telemetry hosts
    TELEMETRY_HOSTS = [
        "vortex.data.microsoft.com",
        "vortex-win.data.microsoft.com",
        "telecommand.telemetry.microsoft.com",
        "telecommand.telemetry.microsoft.com.nsatc.net",
        "oca.telemetry.microsoft.com",
        "oca.telemetry.microsoft.com.nsatc.net",
        "sqm.telemetry.microsoft.com",
        "sqm.telemetry.microsoft.com.nsatc.net",
        "watson.telemetry.microsoft.com",
        "watson.telemetry.microsoft.com.nsatc.net",
        "redir.metaservices.microsoft.com",
        "choice.microsoft.com",
        "choice.microsoft.com.nsatc.net",
        "df.telemetry.microsoft.com",
        "reports.wes.df.telemetry.microsoft.com",
        "wes.df.telemetry.microsoft.com",
        "services.wes.df.telemetry.microsoft.com",
        "sqm.df.telemetry.microsoft.com",
        "telemetry.microsoft.com",
        "watson.ppe.telemetry.microsoft.com",
        "telemetry.appex.bing.net",
        "telemetry.urs.microsoft.com",
        "telemetry.appex.bing.net:443",
        "settings-sandbox.data.microsoft.com",
        "survey.watson.microsoft.com",
        "watson.live.com",
        "statsfe2.ws.microsoft.com",
        "corpext.msitadfs.glbdns2.microsoft.com",
        "compatexchange.cloudapp.net",
        "cs1.wpc.v0cdn.net",
        "a-0001.a-msedge.net",
        "statsfe2.update.microsoft.com.akadns.net",
        "sls.update.microsoft.com.akadns.net",
        "fe2.update.microsoft.com.akadns.net",
        "diagnostics.support.microsoft.com",
        "corp.sts.microsoft.com",
        "statsfe1.ws.microsoft.com",
        "pre.footprintpredict.com",
        "i1.services.social.microsoft.com",
        "i1.services.social.microsoft.com.nsatc.net",
        "feedback.windows.com",
        "feedback.microsoft-hohm.com",
        "feedback.search.microsoft.com",
    ]

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.registry = RegistryManager()
        self._changes: list[dict[str, Any]] = []

    def get_tasks(self) -> list[OptimizationTask]:
        """Get all privacy tasks"""
        return [
            OptimizationTask(
                name="disable_telemetry",
                description="Disable Windows telemetry data collection",
                category=OptimizationCategory.PRIVACY,
                level=OptimizationLevel.SAFE,
                execute=self.disable_telemetry,
                rollback=self._rollback_registry,
                requires_admin=True,
            ),
            OptimizationTask(
                name="disable_advertising_id",
                description="Disable advertising ID and personalization",
                category=OptimizationCategory.PRIVACY,
                level=OptimizationLevel.SAFE,
                execute=self.disable_advertising_id,
                rollback=self._rollback_registry,
                requires_admin=False,
            ),
            OptimizationTask(
                name="disable_cortana",
                description="Disable Cortana and web search",
                category=OptimizationCategory.PRIVACY,
                level=OptimizationLevel.MODERATE,
                execute=self.disable_cortana,
                rollback=self._rollback_registry,
                requires_admin=False,
            ),
            OptimizationTask(
                name="disable_activity_history",
                description="Disable activity history and timeline",
                category=OptimizationCategory.PRIVACY,
                level=OptimizationLevel.SAFE,
                execute=self.disable_activity_history,
                rollback=self._rollback_registry,
                requires_admin=False,
            ),
            OptimizationTask(
                name="disable_location",
                description="Disable location services",
                category=OptimizationCategory.PRIVACY,
                level=OptimizationLevel.MODERATE,
                execute=self.disable_location,
                rollback=self._rollback_registry,
                requires_admin=True,
            ),
            OptimizationTask(
                name="disable_telemetry_tasks",
                description="Disable telemetry scheduled tasks",
                category=OptimizationCategory.PRIVACY,
                level=OptimizationLevel.MODERATE,
                execute=self.disable_telemetry_tasks,
                requires_admin=True,
            ),
            OptimizationTask(
                name="block_telemetry_hosts",
                description="Block telemetry hosts via hosts file",
                category=OptimizationCategory.PRIVACY,
                level=OptimizationLevel.AGGRESSIVE,
                execute=self.block_telemetry_hosts,
                rollback=self._rollback_hosts,
                requires_admin=True,
            ),
            OptimizationTask(
                name="disable_diagnostic_data",
                description="Set diagnostic data to minimum",
                category=OptimizationCategory.PRIVACY,
                level=OptimizationLevel.SAFE,
                execute=self.disable_diagnostic_data,
                rollback=self._rollback_registry,
                requires_admin=True,
            ),
        ]

    def _set_registry_values(
        self, tweaks: list[tuple[str, str, Any, RegistryValueType]], operation: str
    ) -> OptimizationResult:
        """Apply a list of registry tweaks"""
        success_count = 0
        fail_count = 0
        rollback_data = []

        for path, name, value, value_type in tweaks:
            # Save original value for rollback
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
            module="privacy",
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

    def _rollback_hosts(self, data: dict) -> bool:
        """Rollback hosts file changes"""
        if "hosts_backup" not in data:
            return False

        hosts_path = Path(r"C:\Windows\System32\drivers\etc\hosts")
        try:
            guard_mutation(f"overwrite {hosts_path}", legacy=True)
            hosts_path.write_text(data["hosts_backup"])
            return True
        except Exception as e:
            logger.error(f"Failed to restore hosts file: {e}")
            return False

    def disable_telemetry(self) -> OptimizationResult:
        """Disable Windows telemetry via registry"""
        tweaks = RegistryTweaks.disable_telemetry()
        return self._set_registry_values(tweaks, "disable_telemetry")

    def disable_advertising_id(self) -> OptimizationResult:
        """Disable advertising ID"""
        tweaks = RegistryTweaks.disable_advertising_id()
        return self._set_registry_values(tweaks, "disable_advertising_id")

    def disable_cortana(self) -> OptimizationResult:
        """Disable Cortana and web search"""
        tweaks = RegistryTweaks.disable_cortana()
        return self._set_registry_values(tweaks, "disable_cortana")

    def disable_activity_history(self) -> OptimizationResult:
        """Disable activity history and timeline"""
        tweaks = [
            (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\System", "EnableActivityFeed", 0, RegistryValueType.DWORD),
            (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\System", "PublishUserActivities", 0, RegistryValueType.DWORD),
            (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\System", "UploadUserActivities", 0, RegistryValueType.DWORD),
        ]
        return self._set_registry_values(tweaks, "disable_activity_history")

    def disable_location(self) -> OptimizationResult:
        """Disable location services"""
        tweaks = [
            (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors", "DisableLocation", 1, RegistryValueType.DWORD),
            (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors", "DisableLocationScripting", 1, RegistryValueType.DWORD),
            (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors", "DisableWindowsLocationProvider", 1, RegistryValueType.DWORD),
            (r"HKCU\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location", "Value", "Deny", RegistryValueType.STRING),
        ]
        return self._set_registry_values(tweaks, "disable_location")

    def disable_diagnostic_data(self) -> OptimizationResult:
        """Set diagnostic data collection to minimum (Security only on Enterprise, Basic otherwise)"""
        tweaks = [
            (RegistryPaths.TELEMETRY, "AllowTelemetry", 0, RegistryValueType.DWORD),
            (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection", "LimitEnhancedDiagnosticDataWindowsAnalytics", 1, RegistryValueType.DWORD),
            (r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection", "AllowTelemetry", 0, RegistryValueType.DWORD),
            (r"HKCU\Software\Microsoft\Windows\CurrentVersion\Privacy", "TailoredExperiencesWithDiagnosticDataEnabled", 0, RegistryValueType.DWORD),
        ]
        return self._set_registry_values(tweaks, "disable_diagnostic_data")

    def disable_telemetry_tasks(self) -> OptimizationResult:
        """Disable telemetry-related scheduled tasks"""
        disabled = 0
        failed = 0
        task_results = []

        for task in self.TELEMETRY_TASKS:
            try:
                if self.dry_run:
                    disabled += 1
                    continue

                result = guarded_run(
                    ["schtasks", "/Change", "/TN", task, "/Disable"],
                    timeout=10,
                )

                if result.returncode == 0:
                    disabled += 1
                    task_results.append({"task": task, "status": "disabled"})
                else:
                    failed += 1
                    task_results.append({"task": task, "status": "failed", "error": result.stderr})

            except Exception as e:
                failed += 1
                task_results.append({"task": task, "status": "error", "error": str(e)})

        return OptimizationResult(
            success=failed == 0,
            module="privacy",
            operation="disable_telemetry_tasks",
            message=f"Disabled {disabled}/{disabled + failed} telemetry tasks",
            details={"tasks": task_results},
        )

    def block_telemetry_hosts(self) -> OptimizationResult:
        """Block telemetry hosts via Windows hosts file"""
        hosts_path = Path(r"C:\Windows\System32\drivers\etc\hosts")

        try:
            # Read current hosts file
            original_content = ""
            if hosts_path.exists():
                original_content = hosts_path.read_text()

            # Check if we've already added our blocks
            marker = "# WindowsOptimizerAbso Telemetry Block"
            if marker in original_content:
                return OptimizationResult(
                    success=True,
                    module="privacy",
                    operation="block_telemetry_hosts",
                    message="Telemetry hosts already blocked",
                )

            if self.dry_run:
                return OptimizationResult(
                    success=True,
                    module="privacy",
                    operation="block_telemetry_hosts",
                    message=f"[DRY RUN] Would block {len(self.TELEMETRY_HOSTS)} hosts",
                    rollback_data={"hosts_backup": original_content},
                )

            # Build new entries
            new_entries = ["\n", marker, "# Added by WindowsOptimizerAbso - Do not edit this section"]
            for host in self.TELEMETRY_HOSTS:
                new_entries.append(f"0.0.0.0 {host}")
            new_entries.append(f"# End {marker}\n")

            # Append to hosts file
            new_content = original_content + "\n".join(new_entries)
            guard_mutation(f"append telemetry host blocks to {hosts_path}", legacy=True)
            hosts_path.write_text(new_content)

            # Flush DNS cache
            guarded_run(["ipconfig", "/flushdns"], timeout=10)

            return OptimizationResult(
                success=True,
                module="privacy",
                operation="block_telemetry_hosts",
                message=f"Blocked {len(self.TELEMETRY_HOSTS)} telemetry hosts",
                rollback_data={"hosts_backup": original_content},
            )

        except PermissionError:
            return OptimizationResult(
                success=False,
                module="privacy",
                operation="block_telemetry_hosts",
                message="Permission denied - run as administrator",
            )
        except Exception as e:
            return OptimizationResult(
                success=False,
                module="privacy",
                operation="block_telemetry_hosts",
                message=f"Failed: {e}",
            )

    def analyze(self) -> dict[str, Any]:
        """Analyze current privacy settings"""
        analysis = {
            "telemetry_enabled": True,
            "advertising_id_enabled": True,
            "cortana_enabled": True,
            "location_enabled": True,
            "activity_history_enabled": True,
            "telemetry_hosts_blocked": False,
            "telemetry_tasks_disabled": 0,
            "telemetry_tasks_total": len(self.TELEMETRY_TASKS),
            "recommendations": [],
        }

        # Check telemetry
        telemetry_value = self.registry.get_value(RegistryPaths.TELEMETRY, "AllowTelemetry")
        if telemetry_value is not None and telemetry_value == 0:
            analysis["telemetry_enabled"] = False
        else:
            analysis["recommendations"].append("Disable telemetry data collection")

        # Check advertising ID
        ad_value = self.registry.get_value(RegistryPaths.ADVERTISING_ID, "Enabled")
        if ad_value is not None and ad_value == 0:
            analysis["advertising_id_enabled"] = False
        else:
            analysis["recommendations"].append("Disable advertising ID")

        # Check Cortana
        cortana_value = self.registry.get_value(RegistryPaths.CORTANA, "AllowCortana")
        if cortana_value is not None and cortana_value == 0:
            analysis["cortana_enabled"] = False
        else:
            analysis["recommendations"].append("Disable Cortana")

        # Check hosts file
        hosts_path = Path(r"C:\Windows\System32\drivers\etc\hosts")
        if hosts_path.exists():
            content = hosts_path.read_text()
            if "WindowsOptimizerAbso Telemetry Block" in content:
                analysis["telemetry_hosts_blocked"] = True
            else:
                analysis["recommendations"].append("Block telemetry hosts")

        # Count disabled telemetry tasks
        for task in self.TELEMETRY_TASKS:
            try:
                result = guarded_run(
                    ["schtasks", "/Query", "/TN", task],
                    timeout=5,
                )
                if "Disabled" in result.stdout:
                    analysis["telemetry_tasks_disabled"] += 1
            except Exception:
                pass

        if analysis["telemetry_tasks_disabled"] < len(self.TELEMETRY_TASKS):
            analysis["recommendations"].append("Disable telemetry scheduled tasks")

        return analysis
