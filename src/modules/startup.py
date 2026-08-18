"""
Startup optimization module
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from ..safety import guard_mutation, guarded_run

from ..core.engine import (
    OptimizationCategory,
    OptimizationLevel,
    OptimizationResult,
    OptimizationTask,
)
from ..core.registry import RegistryManager, RegistryPaths, RegistryValueType


@dataclass
class StartupItem:
    """A startup program entry"""
    name: str
    path: str
    location: str  # Registry path or startup folder
    enabled: bool
    type: str  # "registry", "folder", "task"
    description: str = ""
    publisher: str = ""
    impact: str = ""  # "high", "medium", "low", "not measured"


class StartupModule:
    """
    Startup program management.

    Features:
    - List all startup items
    - Enable/disable startup items
    - Analyze boot time impact
    - Manage scheduled tasks at login
    - Shell extension cleanup
    """

    # Common startup locations
    STARTUP_REGISTRY_PATHS = [
        (r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run", "user"),
        (r"HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce", "user"),
        (r"HKLM\Software\Microsoft\Windows\CurrentVersion\Run", "machine"),
        (r"HKLM\Software\Microsoft\Windows\CurrentVersion\RunOnce", "machine"),
        (r"HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "machine_32bit"),
    ]

    # Known bloatware startup entries that are safe to disable
    BLOATWARE_PATTERNS = [
        "OneDrive",
        "Cortana",
        "Microsoft Teams",
        "Spotify",
        "Discord",
        "Steam Client",
        "Epic Games",
        "Adobe",
        "iTunesHelper",
        "QuickTime",
        "Java Update",
        "CCleaner",
        "Skype",
        "Zoom",
        "Slack",
        "Dropbox",
        "Google Drive",
        "iCloud",
    ]

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.registry = RegistryManager()

    def get_tasks(self) -> list[OptimizationTask]:
        """Get startup optimization tasks"""
        return [
            OptimizationTask(
                name="list_startup_items",
                description="Analyze startup programs",
                category=OptimizationCategory.STARTUP,
                level=OptimizationLevel.SAFE,
                execute=self.analyze_startup,
                requires_admin=False,
            ),
            OptimizationTask(
                name="disable_bloatware_startup",
                description="Disable common bloatware from startup",
                category=OptimizationCategory.STARTUP,
                level=OptimizationLevel.MODERATE,
                execute=self.disable_bloatware,
                rollback=self._rollback_startup,
                requires_admin=False,
            ),
            OptimizationTask(
                name="optimize_boot_config",
                description="Optimize boot configuration",
                category=OptimizationCategory.STARTUP,
                level=OptimizationLevel.MODERATE,
                execute=self.optimize_boot_config,
                requires_admin=True,
            ),
            OptimizationTask(
                name="disable_login_tasks",
                description="Disable unnecessary login scheduled tasks",
                category=OptimizationCategory.STARTUP,
                level=OptimizationLevel.MODERATE,
                execute=self.disable_login_tasks,
                requires_admin=True,
            ),
        ]

    def get_startup_items(self) -> list[StartupItem]:
        """Get all startup items from all locations"""
        items = []

        # Registry startup items
        for reg_path, scope in self.STARTUP_REGISTRY_PATHS:
            items.extend(self._get_registry_startup_items(reg_path, scope))

        # Startup folder items
        items.extend(self._get_folder_startup_items())

        # Scheduled tasks at login
        items.extend(self._get_login_tasks())

        return items

    def _get_registry_startup_items(self, reg_path: str, scope: str) -> list[StartupItem]:
        """Get startup items from a registry location"""
        items = []
        values = self.registry.enumerate_values(reg_path)

        for value in values:
            items.append(StartupItem(
                name=value.name,
                path=str(value.data) if value.data else "",
                location=reg_path,
                enabled=True,
                type="registry",
                description=f"{scope} registry startup",
            ))

        return items

    def _get_folder_startup_items(self) -> list[StartupItem]:
        """Get startup items from startup folders"""
        items = []

        # User startup folder
        user_startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if user_startup.exists():
            for item in user_startup.iterdir():
                if item.suffix.lower() in [".lnk", ".exe", ".bat", ".cmd"]:
                    items.append(StartupItem(
                        name=item.stem,
                        path=str(item),
                        location=str(user_startup),
                        enabled=True,
                        type="folder",
                        description="User startup folder",
                    ))

        # All users startup folder
        all_users_startup = Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if all_users_startup.exists():
            for item in all_users_startup.iterdir():
                if item.suffix.lower() in [".lnk", ".exe", ".bat", ".cmd"]:
                    items.append(StartupItem(
                        name=item.stem,
                        path=str(item),
                        location=str(all_users_startup),
                        enabled=True,
                        type="folder",
                        description="All users startup folder",
                    ))

        return items

    def _get_login_tasks(self) -> list[StartupItem]:
        """Get scheduled tasks that run at login"""
        items = []

        try:
            result = guarded_run(
                ["schtasks", "/Query", "/FO", "CSV", "/V"],
                timeout=30,
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) > 1:
                    # Parse CSV output
                    for line in lines[1:]:
                        try:
                            parts = line.split('","')
                            if len(parts) >= 7:
                                task_name = parts[1].strip('"')
                                trigger = parts[6] if len(parts) > 6 else ""
                                status = parts[3] if len(parts) > 3 else ""

                                # Check if it's a logon trigger
                                if "logon" in trigger.lower() or "At log on" in trigger:
                                    items.append(StartupItem(
                                        name=task_name.split("\\")[-1],
                                        path=task_name,
                                        location="Task Scheduler",
                                        enabled="Disabled" not in status,
                                        type="task",
                                        description="Scheduled task at logon",
                                    ))
                        except Exception:
                            continue

        except Exception as e:
            logger.error(f"Error getting login tasks: {e}")

        return items

    def disable_startup_item(self, item: StartupItem) -> bool:
        """Disable a startup item"""
        if self.dry_run:
            return True

        if item.type == "registry":
            # Move to a disabled key
            disabled_path = item.location.replace("\\Run", "\\Run-Disabled")

            # Get value and delete from original
            value = self.registry.get_value(item.location, item.name)
            if value:
                self.registry.set_value(disabled_path, item.name, value, RegistryValueType.STRING)
                self.registry.delete_value(item.location, item.name)
                return True

        elif item.type == "folder":
            # Rename file with .disabled extension
            path = Path(item.path)
            if path.exists():
                disabled_path = path.with_suffix(path.suffix + ".disabled")
                guard_mutation(f"rename startup item {path} -> {disabled_path}", legacy=True)
                path.rename(disabled_path)
                return True

        elif item.type == "task":
            # Disable scheduled task
            result = guarded_run(
                ["schtasks", "/Change", "/TN", item.path, "/Disable"],
                timeout=10,
            )
            return result.returncode == 0

        return False

    def enable_startup_item(self, item: StartupItem) -> bool:
        """Re-enable a startup item"""
        if self.dry_run:
            return True

        if item.type == "registry":
            disabled_path = item.location.replace("\\Run", "\\Run-Disabled")
            value = self.registry.get_value(disabled_path, item.name)
            if value:
                self.registry.set_value(item.location, item.name, value, RegistryValueType.STRING)
                self.registry.delete_value(disabled_path, item.name)
                return True

        elif item.type == "folder":
            path = Path(item.path)
            if not path.exists():
                disabled_path = Path(str(path) + ".disabled")
                if disabled_path.exists():
                    guard_mutation(f"rename startup item {disabled_path} -> {path}", legacy=True)
                    disabled_path.rename(path)
                    return True

        elif item.type == "task":
            result = guarded_run(
                ["schtasks", "/Change", "/TN", item.path, "/Enable"],
                timeout=10,
            )
            return result.returncode == 0

        return False

    def analyze_startup(self) -> OptimizationResult:
        """Analyze startup programs and their impact"""
        items = self.get_startup_items()

        high_impact = []
        bloatware = []
        total_enabled = 0

        for item in items:
            if item.enabled:
                total_enabled += 1

                # Check for known bloatware
                for pattern in self.BLOATWARE_PATTERNS:
                    if pattern.lower() in item.name.lower() or pattern.lower() in item.path.lower():
                        bloatware.append(item.name)
                        break

        return OptimizationResult(
            success=True,
            module="startup",
            operation="list_startup_items",
            message=f"Found {total_enabled} startup items ({len(bloatware)} bloatware)",
            details={
                "total_items": len(items),
                "enabled_items": total_enabled,
                "bloatware_count": len(bloatware),
                "bloatware": bloatware,
                "items": [
                    {
                        "name": i.name,
                        "path": i.path,
                        "type": i.type,
                        "enabled": i.enabled,
                    }
                    for i in items
                ],
            },
        )

    def disable_bloatware(self) -> OptimizationResult:
        """Disable known bloatware from startup"""
        items = self.get_startup_items()
        disabled = []
        rollback_data = []

        for item in items:
            if not item.enabled:
                continue

            for pattern in self.BLOATWARE_PATTERNS:
                if pattern.lower() in item.name.lower() or pattern.lower() in item.path.lower():
                    if self.disable_startup_item(item):
                        disabled.append(item.name)
                        rollback_data.append({
                            "name": item.name,
                            "path": item.path,
                            "location": item.location,
                            "type": item.type,
                        })
                    break

        return OptimizationResult(
            success=True,
            module="startup",
            operation="disable_bloatware_startup",
            message=f"Disabled {len(disabled)} bloatware startup items",
            details={"disabled": disabled},
            rollback_data={"items": rollback_data},
        )

    def _rollback_startup(self, data: dict) -> bool:
        """Re-enable startup items"""
        if "items" not in data:
            return False

        for item_data in data["items"]:
            item = StartupItem(
                name=item_data["name"],
                path=item_data["path"],
                location=item_data["location"],
                type=item_data["type"],
                enabled=False,
            )
            self.enable_startup_item(item)

        return True

    def optimize_boot_config(self) -> OptimizationResult:
        """Optimize boot configuration for faster startup"""
        tweaks = [
            # Disable boot log
            (r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management", "DisablePagingExecutive", 1, RegistryValueType.DWORD),
            # Prefetch for boot and application
            (r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters", "EnablePrefetcher", 3, RegistryValueType.DWORD),
            (r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters", "EnableSuperfetch", 3, RegistryValueType.DWORD),
            # Boot optimization
            (r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\OptimalLayout", "EnableAutoLayout", 1, RegistryValueType.DWORD),
        ]

        success_count = 0
        for path, name, value, value_type in tweaks:
            if self.dry_run or self.registry.set_value(path, name, value, value_type):
                success_count += 1

        return OptimizationResult(
            success=success_count > 0,
            module="startup",
            operation="optimize_boot_config",
            message=f"Applied {success_count}/{len(tweaks)} boot optimizations",
        )

    def disable_login_tasks(self) -> OptimizationResult:
        """Disable unnecessary scheduled tasks that run at login"""
        login_tasks_to_disable = [
            r"\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser",
            r"\Microsoft\Windows\Application Experience\ProgramDataUpdater",
            r"\Microsoft\Windows\Application Experience\StartupAppTask",
            r"\Microsoft\Windows\Customer Experience Improvement Program\Consolidator",
            r"\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip",
            r"\Microsoft\Windows\DiskDiagnostic\Microsoft-Windows-DiskDiagnosticDataCollector",
            r"\Microsoft\Windows\Maps\MapsToastTask",
            r"\Microsoft\Windows\Maps\MapsUpdateTask",
            r"\Microsoft\Windows\Shell\FamilySafetyMonitor",
            r"\Microsoft\Windows\Shell\FamilySafetyRefresh",
        ]

        disabled = 0
        failed = 0

        for task in login_tasks_to_disable:
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
                else:
                    failed += 1

            except Exception:
                failed += 1

        return OptimizationResult(
            success=failed == 0,
            module="startup",
            operation="disable_login_tasks",
            message=f"Disabled {disabled}/{disabled + failed} login tasks",
        )

    def get_boot_time(self) -> Optional[float]:
        """Get the last boot time in seconds (from Event Log)"""
        try:
            # Query boot time from Event Log using PowerShell
            ps_command = '''
            $bootEvent = Get-WinEvent -FilterHashtable @{LogName='System'; ID=6005} -MaxEvents 1 -ErrorAction SilentlyContinue
            if ($bootEvent) {
                $bootTime = $bootEvent.TimeCreated
                $uptime = (Get-Date) - $bootTime
                Write-Output $uptime.TotalSeconds
            }
            '''
            result = guarded_run(
                # Static script, Get-WinEvent only: observably read-only, so it stays available
                # while the repository is contained. Nothing here is interpolated.
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_command],
                timeout=10,
                mutating=False,
            )

            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())

        except Exception as e:
            logger.error(f"Error getting boot time: {e}")

        return None
