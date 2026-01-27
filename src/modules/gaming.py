"""
Gaming and performance optimization module
"""

from __future__ import annotations

import subprocess
from typing import Any

from loguru import logger

from ..core.engine import (
    OptimizationCategory,
    OptimizationLevel,
    OptimizationResult,
    OptimizationTask,
)
from ..core.registry import RegistryManager, RegistryPaths, RegistryTweaks, RegistryValueType


class GamingModule:
    """
    Gaming and performance optimization.

    Features:
    - Game Mode optimization
    - GPU scheduling
    - Game DVR disable
    - Input lag reduction
    - Power plan optimization
    - Process priority tweaks
    - Memory optimization
    - Fullscreen optimizations
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.registry = RegistryManager()

    def get_tasks(self) -> list[OptimizationTask]:
        """Get gaming optimization tasks"""
        return [
            OptimizationTask(
                name="optimize_game_mode",
                description="Optimize Windows Game Mode settings",
                category=OptimizationCategory.GAMING,
                level=OptimizationLevel.SAFE,
                execute=self.optimize_game_mode,
                rollback=self._rollback_registry,
                requires_admin=False,
            ),
            OptimizationTask(
                name="disable_game_dvr",
                description="Disable Game DVR and Game Bar",
                category=OptimizationCategory.GAMING,
                level=OptimizationLevel.SAFE,
                execute=self.disable_game_dvr,
                rollback=self._rollback_registry,
                requires_admin=False,
            ),
            OptimizationTask(
                name="enable_gpu_scheduling",
                description="Enable hardware-accelerated GPU scheduling",
                category=OptimizationCategory.GAMING,
                level=OptimizationLevel.MODERATE,
                execute=self.enable_gpu_scheduling,
                rollback=self._rollback_registry,
                requires_admin=True,
                requires_reboot=True,
            ),
            OptimizationTask(
                name="reduce_input_lag",
                description="Reduce mouse and input latency",
                category=OptimizationCategory.GAMING,
                level=OptimizationLevel.MODERATE,
                execute=self.reduce_input_lag,
                rollback=self._rollback_registry,
                requires_admin=False,
            ),
            OptimizationTask(
                name="optimize_power_plan",
                description="Set high performance power plan",
                category=OptimizationCategory.GAMING,
                level=OptimizationLevel.SAFE,
                execute=self.optimize_power_plan,
                requires_admin=True,
            ),
            OptimizationTask(
                name="disable_fullscreen_optimizations",
                description="Disable fullscreen optimizations system-wide",
                category=OptimizationCategory.GAMING,
                level=OptimizationLevel.MODERATE,
                execute=self.disable_fullscreen_optimizations,
                rollback=self._rollback_registry,
                requires_admin=True,
            ),
            OptimizationTask(
                name="optimize_nvidia",
                description="Apply NVIDIA-specific optimizations",
                category=OptimizationCategory.GAMING,
                level=OptimizationLevel.MODERATE,
                execute=self.optimize_nvidia,
                requires_admin=False,
            ),
            OptimizationTask(
                name="optimize_memory",
                description="Optimize system memory for gaming",
                category=OptimizationCategory.GAMING,
                level=OptimizationLevel.MODERATE,
                execute=self.optimize_memory,
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
            module="gaming",
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

    def optimize_game_mode(self) -> OptimizationResult:
        """Optimize Game Mode settings"""
        tweaks = [
            # Enable Game Mode
            (RegistryPaths.GAME_BAR, "AllowAutoGameMode", 1, RegistryValueType.DWORD),
            (RegistryPaths.GAME_BAR, "AutoGameModeEnabled", 1, RegistryValueType.DWORD),
            # Disable Game Bar notifications
            (RegistryPaths.GAME_BAR, "ShowStartupPanel", 0, RegistryValueType.DWORD),
            (RegistryPaths.GAME_BAR, "UseNexusForGameBarEnabled", 0, RegistryValueType.DWORD),
            # Game DVR settings
            (RegistryPaths.GAME_DVR, "GameDVR_Enabled", 0, RegistryValueType.DWORD),
            (RegistryPaths.GAME_DVR, "GameDVR_FSEBehavior", 2, RegistryValueType.DWORD),
            (RegistryPaths.GAME_DVR, "GameDVR_FSEBehaviorMode", 2, RegistryValueType.DWORD),
            (RegistryPaths.GAME_DVR, "GameDVR_HonorUserFSEBehaviorMode", 1, RegistryValueType.DWORD),
            (RegistryPaths.GAME_DVR, "GameDVR_DXGIHonorFSEWindowsCompatible", 1, RegistryValueType.DWORD),
        ]

        return self._set_registry_values(tweaks, "optimize_game_mode")

    def disable_game_dvr(self) -> OptimizationResult:
        """Disable Game DVR and Game Bar completely"""
        tweaks = [
            (RegistryPaths.GAME_DVR, "GameDVR_Enabled", 0, RegistryValueType.DWORD),
            (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\GameDVR", "AllowGameDVR", 0, RegistryValueType.DWORD),
            (RegistryPaths.GAME_BAR, "AutoGameModeEnabled", 1, RegistryValueType.DWORD),
            (r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0, RegistryValueType.DWORD),
            (r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR", "AudioCaptureEnabled", 0, RegistryValueType.DWORD),
            (r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR", "CursorCaptureEnabled", 0, RegistryValueType.DWORD),
        ]

        return self._set_registry_values(tweaks, "disable_game_dvr")

    def enable_gpu_scheduling(self) -> OptimizationResult:
        """Enable hardware-accelerated GPU scheduling (Windows 10 2004+)"""
        tweaks = RegistryTweaks.optimize_gaming()

        # Additional GPU scheduling tweaks
        tweaks.extend([
            (RegistryPaths.GPU_SCHEDULING, "HwSchMode", 2, RegistryValueType.DWORD),
            # Disable HDCP
            (r"HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000", "RMHdcpKeyglobZero", 1, RegistryValueType.DWORD),
        ])

        result = self._set_registry_values(tweaks, "enable_gpu_scheduling")
        result.requires_reboot = True
        result.message += " (reboot required)"

        return result

    def reduce_input_lag(self) -> OptimizationResult:
        """Reduce mouse and input latency"""
        tweaks = [
            # Disable mouse acceleration
            (RegistryPaths.MOUSE, "MouseSpeed", "0", RegistryValueType.STRING),
            (RegistryPaths.MOUSE, "MouseThreshold1", "0", RegistryValueType.STRING),
            (RegistryPaths.MOUSE, "MouseThreshold2", "0", RegistryValueType.STRING),
            # Keyboard response
            (r"HKCU\Control Panel\Keyboard", "KeyboardDelay", "0", RegistryValueType.STRING),
            (r"HKCU\Control Panel\Keyboard", "KeyboardSpeed", "31", RegistryValueType.STRING),
            # Raw input
            (r"HKCU\Control Panel\Mouse", "MouseSensitivity", "10", RegistryValueType.STRING),
            # Disable pointer precision
            (RegistryPaths.MOUSE, "MouseHoverTime", "10", RegistryValueType.STRING),
        ]

        return self._set_registry_values(tweaks, "reduce_input_lag")

    def optimize_power_plan(self) -> OptimizationResult:
        """Set High Performance or Ultimate Performance power plan"""
        try:
            if self.dry_run:
                return OptimizationResult(
                    success=True,
                    module="gaming",
                    operation="optimize_power_plan",
                    message="[DRY RUN] Would set High Performance power plan",
                )

            # Try to enable Ultimate Performance plan first (hidden by default)
            subprocess.run(
                ["powercfg", "-duplicatescheme", "e9a42b02-d5df-448d-aa00-03f14749eb61"],
                capture_output=True,
                timeout=10,
            )

            # Get available power plans
            result = subprocess.run(
                ["powercfg", "/list"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            # Find High Performance or Ultimate Performance GUID
            plan_guid = None
            for line in result.stdout.splitlines():
                if "High performance" in line or "Ultimate Performance" in line:
                    # Extract GUID
                    parts = line.split()
                    for part in parts:
                        if len(part) == 36 and part.count("-") == 4:
                            plan_guid = part
                            break
                    if plan_guid:
                        break

            if not plan_guid:
                # Use known High Performance GUID
                plan_guid = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"

            # Set the power plan
            result = subprocess.run(
                ["powercfg", "/setactive", plan_guid],
                capture_output=True,
                timeout=10,
            )

            if result.returncode == 0:
                return OptimizationResult(
                    success=True,
                    module="gaming",
                    operation="optimize_power_plan",
                    message="High Performance power plan activated",
                )
            else:
                return OptimizationResult(
                    success=False,
                    module="gaming",
                    operation="optimize_power_plan",
                    message="Failed to set power plan",
                )

        except Exception as e:
            return OptimizationResult(
                success=False,
                module="gaming",
                operation="optimize_power_plan",
                message=f"Error: {e}",
            )

    def disable_fullscreen_optimizations(self) -> OptimizationResult:
        """Disable fullscreen optimizations system-wide"""
        tweaks = [
            # Disable fullscreen optimizations for all apps
            (r"HKCU\System\GameConfigStore", "GameDVR_FSEBehavior", 2, RegistryValueType.DWORD),
            (r"HKCU\System\GameConfigStore", "GameDVR_FSEBehaviorMode", 2, RegistryValueType.DWORD),
            (r"HKCU\System\GameConfigStore", "GameDVR_HonorUserFSEBehaviorMode", 1, RegistryValueType.DWORD),
            (r"HKCU\System\GameConfigStore", "GameDVR_DXGIHonorFSEWindowsCompatible", 1, RegistryValueType.DWORD),
            (r"HKCU\System\GameConfigStore", "GameDVR_EFSEFeatureFlags", 0, RegistryValueType.DWORD),
            # Disable DWM for fullscreen apps
            (r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment", "DISABLE_DWM_COMPOSITION_FOR_GAMES", "1", RegistryValueType.STRING),
        ]

        return self._set_registry_values(tweaks, "disable_fullscreen_optimizations")

    def optimize_nvidia(self) -> OptimizationResult:
        """Apply NVIDIA-specific optimizations"""
        # Check if NVIDIA driver is installed
        nvidia_path = r"HKLM\SOFTWARE\NVIDIA Corporation\Global\NVTweak"

        tweaks = [
            # NVIDIA optimizations
            (nvidia_path, "Gestalt", 1, RegistryValueType.DWORD),
            # Shader cache
            (r"HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "TdrDelay", 10, RegistryValueType.DWORD),
            (r"HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "TdrDdiDelay", 10, RegistryValueType.DWORD),
            # Disable NVIDIA telemetry tasks (via registry flag)
            (r"HKLM\SOFTWARE\NVIDIA Corporation\NvControlPanel2\Client", "OptInOrOutPreference", 0, RegistryValueType.DWORD),
        ]

        result = self._set_registry_values(tweaks, "optimize_nvidia")

        # Try to disable NVIDIA telemetry services
        nvidia_services = [
            "NvTelemetryContainer",
            "NVDisplay.ContainerLocalSystem",
        ]

        for svc in nvidia_services:
            try:
                if not self.dry_run:
                    subprocess.run(
                        ["sc", "config", svc, "start=", "disabled"],
                        capture_output=True,
                        timeout=10,
                    )
            except Exception:
                pass

        return result

    def optimize_memory(self) -> OptimizationResult:
        """Optimize system memory for gaming"""
        tweaks = [
            # Disable memory compression
            (r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management", "DisablePagingCombining", 1, RegistryValueType.DWORD),
            # Large system cache
            (r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management", "LargeSystemCache", 0, RegistryValueType.DWORD),
            # Disable paging executive
            (r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management", "DisablePagingExecutive", 1, RegistryValueType.DWORD),
            # Clear page file on shutdown (security + clean start)
            (r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management", "ClearPageFileAtShutdown", 0, RegistryValueType.DWORD),
            # Second level data cache size (set to your CPU's L2 cache in KB, default to 256)
            (r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management", "SecondLevelDataCache", 256, RegistryValueType.DWORD),
        ]

        return self._set_registry_values(tweaks, "optimize_memory")

    def analyze(self) -> dict[str, Any]:
        """Analyze current gaming configuration"""
        analysis = {
            "game_mode": {},
            "gpu_scheduling": False,
            "power_plan": "unknown",
            "recommendations": [],
        }

        # Check Game Mode
        game_mode = self.registry.get_value(RegistryPaths.GAME_BAR, "AutoGameModeEnabled")
        analysis["game_mode"]["enabled"] = game_mode == 1

        # Check Game DVR
        game_dvr = self.registry.get_value(RegistryPaths.GAME_DVR, "GameDVR_Enabled")
        analysis["game_mode"]["dvr_disabled"] = game_dvr == 0

        # Check GPU scheduling
        gpu_sched = self.registry.get_value(RegistryPaths.GPU_SCHEDULING, "HwSchMode")
        analysis["gpu_scheduling"] = gpu_sched == 2

        # Check power plan
        try:
            result = subprocess.run(
                ["powercfg", "/getactivescheme"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                if "High performance" in result.stdout:
                    analysis["power_plan"] = "high_performance"
                elif "Ultimate" in result.stdout:
                    analysis["power_plan"] = "ultimate_performance"
                elif "Balanced" in result.stdout:
                    analysis["power_plan"] = "balanced"
                else:
                    analysis["power_plan"] = "other"
        except Exception:
            pass

        # Generate recommendations
        if not analysis["game_mode"]["enabled"]:
            analysis["recommendations"].append("Enable Game Mode")

        if not analysis["game_mode"]["dvr_disabled"]:
            analysis["recommendations"].append("Disable Game DVR for better performance")

        if not analysis["gpu_scheduling"]:
            analysis["recommendations"].append("Enable Hardware-Accelerated GPU Scheduling")

        if analysis["power_plan"] not in ["high_performance", "ultimate_performance"]:
            analysis["recommendations"].append("Switch to High Performance power plan")

        return analysis
