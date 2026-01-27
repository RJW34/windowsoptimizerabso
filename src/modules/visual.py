"""
Visual effects and UI performance optimization module
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
from ..core.registry import RegistryManager, RegistryValueType


class VisualModule:
    """
    Visual effects optimization for better performance.

    Features:
    - Disable Windows animations
    - Reduce visual effects
    - Optimize transparency settings
    - Disable Aero effects
    - Font smoothing options
    - Taskbar optimization
    """

    # Registry paths for visual settings
    DESKTOP_PATH = r"HKCU\Control Panel\Desktop"
    WINDOW_METRICS = r"HKCU\Control Panel\Desktop\WindowMetrics"
    VISUAL_EFFECTS = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"
    ADVANCED_PATH = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
    DWM_PATH = r"HKCU\Software\Microsoft\Windows\DWM"
    THEMES_PATH = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.registry = RegistryManager()

    def get_tasks(self) -> list[OptimizationTask]:
        """Get visual optimization tasks"""
        return [
            OptimizationTask(
                name="disable_animations",
                description="Disable window animations and transitions",
                category=OptimizationCategory.VISUAL,
                level=OptimizationLevel.SAFE,
                execute=self.disable_animations,
                rollback=self._rollback_registry,
                requires_admin=False,
            ),
            OptimizationTask(
                name="optimize_visual_effects",
                description="Set Windows visual effects to best performance",
                category=OptimizationCategory.VISUAL,
                level=OptimizationLevel.SAFE,
                execute=self.optimize_visual_effects,
                rollback=self._rollback_registry,
                requires_admin=False,
            ),
            OptimizationTask(
                name="disable_transparency",
                description="Disable transparency effects",
                category=OptimizationCategory.VISUAL,
                level=OptimizationLevel.SAFE,
                execute=self.disable_transparency,
                rollback=self._rollback_registry,
                requires_admin=False,
            ),
            OptimizationTask(
                name="optimize_taskbar",
                description="Optimize taskbar for performance",
                category=OptimizationCategory.VISUAL,
                level=OptimizationLevel.SAFE,
                execute=self.optimize_taskbar,
                rollback=self._rollback_registry,
                requires_admin=False,
            ),
            OptimizationTask(
                name="disable_cursor_effects",
                description="Disable cursor shadow and trails",
                category=OptimizationCategory.VISUAL,
                level=OptimizationLevel.SAFE,
                execute=self.disable_cursor_effects,
                rollback=self._rollback_registry,
                requires_admin=False,
            ),
            OptimizationTask(
                name="optimize_font_rendering",
                description="Optimize font rendering (ClearType)",
                category=OptimizationCategory.VISUAL,
                level=OptimizationLevel.SAFE,
                execute=self.optimize_font_rendering,
                rollback=self._rollback_registry,
                requires_admin=False,
            ),
            OptimizationTask(
                name="disable_dwm_effects",
                description="Reduce Desktop Window Manager effects",
                category=OptimizationCategory.VISUAL,
                level=OptimizationLevel.MODERATE,
                execute=self.disable_dwm_effects,
                rollback=self._rollback_registry,
                requires_admin=False,
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
            module="visual",
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

    def disable_animations(self) -> OptimizationResult:
        """Disable window animations and transitions"""
        tweaks = [
            # Disable menu animation
            (self.DESKTOP_PATH, "MenuShowDelay", "0", RegistryValueType.STRING),
            # Disable window animations
            (self.DESKTOP_PATH, "DragFullWindows", "0", RegistryValueType.STRING),
            # Disable minimize/maximize animations
            (self.WINDOW_METRICS, "MinAnimate", "0", RegistryValueType.STRING),
            # Disable taskbar animations
            (self.ADVANCED_PATH, "TaskbarAnimations", 0, RegistryValueType.DWORD),
            # Disable Start menu animations
            (self.ADVANCED_PATH, "StartMenuFadeEffect", 0, RegistryValueType.DWORD),
            # Fast tooltips
            (self.DESKTOP_PATH, "ToolTipDelay", "200", RegistryValueType.STRING),
        ]

        result = self._set_registry_values(tweaks, "disable_animations")

        # Apply UserPreferencesMask for additional animation control
        if not self.dry_run:
            self._set_user_preferences_mask(disable_animations=True)

        return result

    def optimize_visual_effects(self) -> OptimizationResult:
        """Set Windows visual effects to best performance"""
        tweaks = [
            # Set visual effects to "Adjust for best performance"
            (self.VISUAL_EFFECTS, "VisualFXSetting", 2, RegistryValueType.DWORD),
            # Disable individual effects
            (self.ADVANCED_PATH, "ListviewAlphaSelect", 0, RegistryValueType.DWORD),
            (self.ADVANCED_PATH, "ListviewShadow", 0, RegistryValueType.DWORD),
            (self.ADVANCED_PATH, "IconsOnly", 0, RegistryValueType.DWORD),
            # Disable peek at desktop
            (self.ADVANCED_PATH, "DisablePreviewDesktop", 1, RegistryValueType.DWORD),
            # Disable thumbnails in taskbar
            (self.ADVANCED_PATH, "ExtendedUIHoverTime", 30000, RegistryValueType.DWORD),
        ]

        return self._set_registry_values(tweaks, "optimize_visual_effects")

    def disable_transparency(self) -> OptimizationResult:
        """Disable transparency effects"""
        tweaks = [
            # Disable transparency in Windows 10/11
            (self.THEMES_PATH, "EnableTransparency", 0, RegistryValueType.DWORD),
            # DWM transparency
            (self.DWM_PATH, "EnableAeroPeek", 0, RegistryValueType.DWORD),
            (self.DWM_PATH, "AlwaysHibernateThumbnails", 0, RegistryValueType.DWORD),
            # Disable Aero Glass
            (self.DWM_PATH, "Composition", 0, RegistryValueType.DWORD),
            (self.DWM_PATH, "ColorizationOpaqueBlend", 1, RegistryValueType.DWORD),
        ]

        return self._set_registry_values(tweaks, "disable_transparency")

    def optimize_taskbar(self) -> OptimizationResult:
        """Optimize taskbar for performance"""
        tweaks = [
            # Disable taskbar animations
            (self.ADVANCED_PATH, "TaskbarAnimations", 0, RegistryValueType.DWORD),
            # Disable taskbar transparency
            (self.ADVANCED_PATH, "TaskbarGlomLevel", 1, RegistryValueType.DWORD),
            # Disable show thumbnails
            (self.ADVANCED_PATH, "DisablePreviewWindow", 1, RegistryValueType.DWORD),
            # Disable people button
            (self.ADVANCED_PATH, "PeopleBand", 0, RegistryValueType.DWORD),
            # Disable news and interests (Windows 10)
            (r"HKCU\Software\Microsoft\Windows\CurrentVersion\Feeds", "ShellFeedsTaskbarViewMode", 2, RegistryValueType.DWORD),
            # Disable widgets (Windows 11)
            (r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "TaskbarDa", 0, RegistryValueType.DWORD),
            # Disable chat icon (Windows 11)
            (r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "TaskbarMn", 0, RegistryValueType.DWORD),
        ]

        return self._set_registry_values(tweaks, "optimize_taskbar")

    def disable_cursor_effects(self) -> OptimizationResult:
        """Disable cursor shadow and trails"""
        tweaks = [
            # Disable cursor shadow
            (self.DESKTOP_PATH, "CursorShadow", "0", RegistryValueType.STRING),
            # Disable mouse trails
            (r"HKCU\Control Panel\Mouse", "MouseTrails", "0", RegistryValueType.STRING),
            # Disable snap cursor to default button
            (r"HKCU\Control Panel\Mouse", "SnapToDefaultButton", "0", RegistryValueType.STRING),
        ]

        return self._set_registry_values(tweaks, "disable_cursor_effects")

    def optimize_font_rendering(self) -> OptimizationResult:
        """Optimize font rendering with ClearType"""
        tweaks = [
            # Enable ClearType
            (self.DESKTOP_PATH, "FontSmoothing", "2", RegistryValueType.STRING),
            (self.DESKTOP_PATH, "FontSmoothingType", 2, RegistryValueType.DWORD),
            # Font smoothing orientation (RGB)
            (self.DESKTOP_PATH, "FontSmoothingOrientation", 1, RegistryValueType.DWORD),
            # Font smoothing gamma
            (self.DESKTOP_PATH, "FontSmoothingGamma", 1200, RegistryValueType.DWORD),
        ]

        return self._set_registry_values(tweaks, "optimize_font_rendering")

    def disable_dwm_effects(self) -> OptimizationResult:
        """Reduce Desktop Window Manager effects"""
        tweaks = [
            # Disable DWM blur
            (self.DWM_PATH, "EnableBlurBehind", 0, RegistryValueType.DWORD),
            # Disable Flip3D (legacy)
            (self.DWM_PATH, "Flip3DPolicy", 0, RegistryValueType.DWORD),
            # Reduce DWM compositor latency
            (self.DWM_PATH, "ForceEffectMode", 0, RegistryValueType.DWORD),
            # Disable window shadow
            (r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "ListviewShadow", 0, RegistryValueType.DWORD),
            # Disable drop shadows on windows
            (self.DESKTOP_PATH, "UserPreferencesMask", bytes([0x90, 0x12, 0x03, 0x80, 0x10, 0x00, 0x00, 0x00]), RegistryValueType.BINARY),
        ]

        return self._set_registry_values(tweaks, "disable_dwm_effects")

    def _set_user_preferences_mask(self, disable_animations: bool = True) -> None:
        """Set UserPreferencesMask for animation control"""
        # The UserPreferencesMask is a binary value that controls various UI settings
        # Value breakdown (each bit controls a feature):
        # Byte 0: Window animations, smooth scrolling, etc.
        # Byte 1: Menu animations, tooltips
        # We set it to disable animations while keeping essentials

        if disable_animations:
            # Performance mode: minimal animations
            mask = bytes([0x90, 0x12, 0x03, 0x80, 0x10, 0x00, 0x00, 0x00])
        else:
            # Default Windows appearance
            mask = bytes([0x9E, 0x3E, 0x07, 0x80, 0x12, 0x00, 0x00, 0x00])

        self.registry.set_value(
            self.DESKTOP_PATH,
            "UserPreferencesMask",
            mask,
            RegistryValueType.BINARY,
        )

    def analyze(self) -> dict[str, Any]:
        """Analyze current visual settings"""
        analysis = {
            "animations": {},
            "transparency": {},
            "visual_effects": {},
            "recommendations": [],
        }

        # Check animation settings
        menu_delay = self.registry.get_value(self.DESKTOP_PATH, "MenuShowDelay")
        analysis["animations"]["menu_delay"] = menu_delay or "400"

        min_animate = self.registry.get_value(self.WINDOW_METRICS, "MinAnimate")
        analysis["animations"]["minimize_animate"] = min_animate == "1"

        taskbar_anim = self.registry.get_value(self.ADVANCED_PATH, "TaskbarAnimations")
        analysis["animations"]["taskbar_animations"] = taskbar_anim == 1

        # Check transparency
        transparency = self.registry.get_value(self.THEMES_PATH, "EnableTransparency")
        analysis["transparency"]["enabled"] = transparency == 1

        aero_peek = self.registry.get_value(self.DWM_PATH, "EnableAeroPeek")
        analysis["transparency"]["aero_peek"] = aero_peek == 1

        # Check visual effects level
        vfx_setting = self.registry.get_value(self.VISUAL_EFFECTS, "VisualFXSetting")
        settings_map = {0: "let_windows_decide", 1: "best_appearance", 2: "best_performance", 3: "custom"}
        analysis["visual_effects"]["mode"] = settings_map.get(vfx_setting, "unknown")

        # Generate recommendations
        if analysis["animations"]["minimize_animate"]:
            analysis["recommendations"].append("Disable minimize/maximize animations")

        if analysis["animations"]["taskbar_animations"]:
            analysis["recommendations"].append("Disable taskbar animations")

        if analysis["transparency"]["enabled"]:
            analysis["recommendations"].append("Disable transparency for better performance")

        if analysis["visual_effects"]["mode"] != "best_performance":
            analysis["recommendations"].append("Set visual effects to best performance")

        return analysis

    def apply_preset(self, preset: str) -> OptimizationResult:
        """
        Apply a visual preset.

        Presets:
        - performance: Maximum performance, minimal visuals
        - balanced: Good performance with some visual polish
        - appearance: Full visual effects (restore defaults)
        """
        if preset == "performance":
            # Apply all performance optimizations
            results = []
            results.append(self.disable_animations())
            results.append(self.optimize_visual_effects())
            results.append(self.disable_transparency())
            results.append(self.disable_cursor_effects())
            results.append(self.disable_dwm_effects())

            success = all(r.success for r in results)
            return OptimizationResult(
                success=success,
                module="visual",
                operation="apply_preset_performance",
                message=f"Applied performance preset ({sum(1 for r in results if r.success)}/{len(results)} successful)",
            )

        elif preset == "balanced":
            tweaks = [
                # Keep some effects but disable heavy ones
                (self.DESKTOP_PATH, "MenuShowDelay", "100", RegistryValueType.STRING),
                (self.ADVANCED_PATH, "TaskbarAnimations", 0, RegistryValueType.DWORD),
                (self.THEMES_PATH, "EnableTransparency", 0, RegistryValueType.DWORD),
                (self.WINDOW_METRICS, "MinAnimate", "1", RegistryValueType.STRING),
                (self.VISUAL_EFFECTS, "VisualFXSetting", 3, RegistryValueType.DWORD),  # Custom
            ]
            return self._set_registry_values(tweaks, "apply_preset_balanced")

        elif preset == "appearance":
            # Restore default Windows appearance
            tweaks = [
                (self.DESKTOP_PATH, "MenuShowDelay", "400", RegistryValueType.STRING),
                (self.DESKTOP_PATH, "DragFullWindows", "1", RegistryValueType.STRING),
                (self.WINDOW_METRICS, "MinAnimate", "1", RegistryValueType.STRING),
                (self.ADVANCED_PATH, "TaskbarAnimations", 1, RegistryValueType.DWORD),
                (self.THEMES_PATH, "EnableTransparency", 1, RegistryValueType.DWORD),
                (self.DWM_PATH, "EnableAeroPeek", 1, RegistryValueType.DWORD),
                (self.VISUAL_EFFECTS, "VisualFXSetting", 1, RegistryValueType.DWORD),  # Best appearance
            ]
            return self._set_registry_values(tweaks, "apply_preset_appearance")

        else:
            return OptimizationResult(
                success=False,
                module="visual",
                operation="apply_preset",
                message=f"Unknown preset: {preset}. Use 'performance', 'balanced', or 'appearance'",
            )
