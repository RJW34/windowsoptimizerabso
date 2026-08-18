"""
System cleanup module - temp files, caches, logs, etc.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Optional

from loguru import logger

from ..safety import guard_mutation, guarded_run

from ..core.engine import (
    OptimizationCategory,
    OptimizationLevel,
    OptimizationResult,
    OptimizationTask,
)


@dataclass
class CleanupTarget:
    """A target for cleanup operations"""
    name: str
    path: Path
    pattern: str = "*"
    recursive: bool = True
    min_age_days: int = 0  # Only delete files older than this
    safe: bool = True
    description: str = ""


@dataclass
class CleanupResult:
    """Result of a cleanup operation"""
    target: str
    files_deleted: int
    bytes_freed: int
    errors: list[str]


class CleanupModule:
    """
    System cleanup operations.

    Targets:
    - Windows temp files
    - User temp files
    - Browser caches
    - Windows Update cleanup
    - Prefetch (optional)
    - Thumbnail cache
    - Log files
    - Recycle Bin
    - Memory dumps
    """

    # Standard cleanup targets
    TARGETS: list[CleanupTarget] = [
        CleanupTarget(
            name="windows_temp",
            path=Path(os.environ.get("WINDIR", "C:\\Windows")) / "Temp",
            description="Windows temporary files",
        ),
        CleanupTarget(
            name="user_temp",
            path=Path(os.environ.get("TEMP", "C:\\Users\\Default\\AppData\\Local\\Temp")),
            description="User temporary files",
        ),
        CleanupTarget(
            name="prefetch",
            path=Path(os.environ.get("WINDIR", "C:\\Windows")) / "Prefetch",
            pattern="*.pf",
            min_age_days=7,  # Keep recent prefetch data
            description="Prefetch cache (older than 7 days)",
        ),
        CleanupTarget(
            name="thumbnail_cache",
            path=Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Explorer",
            pattern="thumbcache_*.db",
            description="Thumbnail cache files",
        ),
        CleanupTarget(
            name="windows_logs",
            path=Path(os.environ.get("WINDIR", "C:\\Windows")) / "Logs",
            pattern="*.log",
            min_age_days=30,
            description="Windows log files (older than 30 days)",
        ),
        CleanupTarget(
            name="windows_old_logs",
            path=Path(os.environ.get("WINDIR", "C:\\Windows")) / "Logs" / "CBS",
            pattern="*.log",
            min_age_days=7,
            description="CBS log files",
        ),
        CleanupTarget(
            name="crash_dumps",
            path=Path(os.environ.get("LOCALAPPDATA", "")) / "CrashDumps",
            min_age_days=7,
            description="Application crash dumps",
        ),
        CleanupTarget(
            name="memory_dumps",
            path=Path(os.environ.get("WINDIR", "C:\\Windows")) / "Minidump",
            min_age_days=30,
            description="Memory dump files",
        ),
        CleanupTarget(
            name="delivery_optimization",
            path=Path(os.environ.get("WINDIR", "C:\\Windows")) / "SoftwareDistribution" / "Download",
            min_age_days=7,
            description="Windows Update download cache",
        ),
        CleanupTarget(
            name="font_cache",
            path=Path(os.environ.get("WINDIR", "C:\\Windows")) / "ServiceProfiles" / "LocalService" / "AppData" / "Local" / "FontCache",
            pattern="*.dat",
            description="Font cache files",
        ),
    ]

    # Browser cache locations
    BROWSER_CACHES: list[CleanupTarget] = [
        CleanupTarget(
            name="chrome_cache",
            path=Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Default" / "Cache",
            description="Google Chrome cache",
        ),
        CleanupTarget(
            name="chrome_code_cache",
            path=Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Default" / "Code Cache",
            description="Google Chrome code cache",
        ),
        CleanupTarget(
            name="edge_cache",
            path=Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache",
            description="Microsoft Edge cache",
        ),
        CleanupTarget(
            name="firefox_cache",
            path=Path(os.environ.get("LOCALAPPDATA", "")) / "Mozilla" / "Firefox" / "Profiles",
            pattern="cache2",
            recursive=True,
            description="Mozilla Firefox cache",
        ),
        CleanupTarget(
            name="opera_cache",
            path=Path(os.environ.get("APPDATA", "")) / "Opera Software" / "Opera Stable" / "Cache",
            description="Opera cache",
        ),
        CleanupTarget(
            name="brave_cache",
            path=Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default" / "Cache",
            description="Brave browser cache",
        ),
    ]

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._results: list[CleanupResult] = []

    def get_tasks(self) -> list[OptimizationTask]:
        """Get all cleanup tasks"""
        tasks = [
            OptimizationTask(
                name="cleanup_temp_files",
                description="Clean temporary files",
                category=OptimizationCategory.CLEANUP,
                level=OptimizationLevel.SAFE,
                execute=self.clean_temp_files,
                requires_admin=True,
            ),
            OptimizationTask(
                name="cleanup_browser_cache",
                description="Clean browser caches",
                category=OptimizationCategory.CLEANUP,
                level=OptimizationLevel.SAFE,
                execute=self.clean_browser_caches,
                requires_admin=False,
            ),
            OptimizationTask(
                name="cleanup_windows_update",
                description="Clean Windows Update cache",
                category=OptimizationCategory.CLEANUP,
                level=OptimizationLevel.MODERATE,
                execute=self.clean_windows_update,
                requires_admin=True,
            ),
            OptimizationTask(
                name="cleanup_recycle_bin",
                description="Empty Recycle Bin",
                category=OptimizationCategory.CLEANUP,
                level=OptimizationLevel.SAFE,
                execute=self.empty_recycle_bin,
                requires_admin=False,
            ),
            OptimizationTask(
                name="cleanup_prefetch",
                description="Clean prefetch files",
                category=OptimizationCategory.CLEANUP,
                level=OptimizationLevel.AGGRESSIVE,
                execute=self.clean_prefetch,
                requires_admin=True,
            ),
            OptimizationTask(
                name="cleanup_logs",
                description="Clean old log files",
                category=OptimizationCategory.CLEANUP,
                level=OptimizationLevel.SAFE,
                execute=self.clean_logs,
                requires_admin=True,
            ),
            OptimizationTask(
                name="cleanup_thumbnails",
                description="Clean thumbnail cache",
                category=OptimizationCategory.CLEANUP,
                level=OptimizationLevel.SAFE,
                execute=self.clean_thumbnails,
                requires_admin=False,
            ),
        ]
        return tasks

    def analyze(self) -> dict[str, Any]:
        """Analyze potential cleanup without making changes"""
        analysis = {
            "total_size": 0,
            "targets": [],
        }

        all_targets = self.TARGETS + self.BROWSER_CACHES

        for target in all_targets:
            if not target.path.exists():
                continue

            size = self._get_dir_size(target.path, target.pattern, target.min_age_days)
            if size > 0:
                analysis["targets"].append({
                    "name": target.name,
                    "description": target.description,
                    "path": str(target.path),
                    "size_bytes": size,
                    "size_mb": round(size / (1024 * 1024), 2),
                })
                analysis["total_size"] += size

        analysis["total_size_mb"] = round(analysis["total_size"] / (1024 * 1024), 2)
        analysis["total_size_gb"] = round(analysis["total_size"] / (1024 * 1024 * 1024), 2)

        return analysis

    def _get_dir_size(
        self, path: Path, pattern: str = "*", min_age_days: int = 0
    ) -> int:
        """Calculate size of files matching criteria"""
        total = 0
        cutoff = datetime.now() - timedelta(days=min_age_days) if min_age_days > 0 else None

        try:
            for item in self._iter_files(path, pattern):
                try:
                    if cutoff:
                        mtime = datetime.fromtimestamp(item.stat().st_mtime)
                        if mtime > cutoff:
                            continue
                    total += item.stat().st_size
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            pass

        return total

    def _iter_files(self, path: Path, pattern: str = "*") -> Iterator[Path]:
        """Iterate over files matching pattern"""
        try:
            if pattern == "*":
                yield from path.rglob("*")
            else:
                yield from path.rglob(pattern)
        except (OSError, PermissionError):
            pass

    def _clean_target(self, target: CleanupTarget) -> CleanupResult:
        """Clean a single target"""
        result = CleanupResult(
            target=target.name,
            files_deleted=0,
            bytes_freed=0,
            errors=[],
        )

        if not target.path.exists():
            return result

        cutoff = None
        if target.min_age_days > 0:
            cutoff = datetime.now() - timedelta(days=target.min_age_days)

        for item in self._iter_files(target.path, target.pattern):
            try:
                if not item.is_file():
                    continue

                # Check age
                if cutoff:
                    mtime = datetime.fromtimestamp(item.stat().st_mtime)
                    if mtime > cutoff:
                        continue

                size = item.stat().st_size

                if not self.dry_run:
                    guard_mutation(f"delete file {item}", legacy=True)
                    item.unlink()

                result.files_deleted += 1
                result.bytes_freed += size

            except PermissionError as e:
                result.errors.append(f"Permission denied: {item}")
            except Exception as e:
                result.errors.append(f"Error deleting {item}: {e}")

        logger.info(
            f"Cleaned {target.name}: {result.files_deleted} files, "
            f"{result.bytes_freed / (1024*1024):.1f} MB freed"
        )

        return result

    def clean_temp_files(self) -> OptimizationResult:
        """Clean temporary files"""
        targets = [t for t in self.TARGETS if "temp" in t.name.lower()]
        total_freed = 0
        total_deleted = 0

        for target in targets:
            result = self._clean_target(target)
            total_freed += result.bytes_freed
            total_deleted += result.files_deleted
            self._results.append(result)

        return OptimizationResult(
            success=True,
            module="cleanup",
            operation="cleanup_temp_files",
            message=f"Cleaned {total_deleted} temp files, freed {total_freed / (1024*1024):.1f} MB",
            details={"files_deleted": total_deleted, "bytes_freed": total_freed},
        )

    def clean_browser_caches(self) -> OptimizationResult:
        """Clean browser cache files"""
        total_freed = 0
        total_deleted = 0
        cleaned_browsers = []

        for target in self.BROWSER_CACHES:
            if target.path.exists():
                result = self._clean_target(target)
                total_freed += result.bytes_freed
                total_deleted += result.files_deleted
                self._results.append(result)
                if result.files_deleted > 0:
                    cleaned_browsers.append(target.name.replace("_cache", ""))

        return OptimizationResult(
            success=True,
            module="cleanup",
            operation="cleanup_browser_cache",
            message=f"Cleaned browser caches ({', '.join(cleaned_browsers)}), freed {total_freed / (1024*1024):.1f} MB",
            details={
                "files_deleted": total_deleted,
                "bytes_freed": total_freed,
                "browsers": cleaned_browsers,
            },
        )

    def clean_windows_update(self) -> OptimizationResult:
        """Clean Windows Update cache"""
        # Use Disk Cleanup utility for proper WU cleanup
        try:
            if not self.dry_run:
                # Run cleanmgr with specific switches
                result = guarded_run(
                    ["cleanmgr", "/d", "C:", "/VERYLOWDISK"],
                    timeout=300,
                )

            return OptimizationResult(
                success=True,
                module="cleanup",
                operation="cleanup_windows_update",
                message="Windows Update cleanup initiated",
            )
        except Exception as e:
            return OptimizationResult(
                success=False,
                module="cleanup",
                operation="cleanup_windows_update",
                message=f"Failed: {e}",
            )

    def empty_recycle_bin(self) -> OptimizationResult:
        """Empty the Recycle Bin"""
        try:
            if not self.dry_run:
                # Use PowerShell to clear recycle bin
                guarded_run(
                    ["powershell", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                    timeout=60,
                )

            return OptimizationResult(
                success=True,
                module="cleanup",
                operation="cleanup_recycle_bin",
                message="Recycle Bin emptied",
            )
        except Exception as e:
            return OptimizationResult(
                success=False,
                module="cleanup",
                operation="cleanup_recycle_bin",
                message=f"Failed: {e}",
            )

    def clean_prefetch(self) -> OptimizationResult:
        """Clean prefetch files (use with caution)"""
        target = next((t for t in self.TARGETS if t.name == "prefetch"), None)
        if not target:
            return OptimizationResult(
                success=False,
                module="cleanup",
                operation="cleanup_prefetch",
                message="Prefetch target not found",
            )

        result = self._clean_target(target)
        self._results.append(result)

        return OptimizationResult(
            success=True,
            module="cleanup",
            operation="cleanup_prefetch",
            message=f"Cleaned {result.files_deleted} prefetch files, freed {result.bytes_freed / (1024*1024):.1f} MB",
            details={"files_deleted": result.files_deleted, "bytes_freed": result.bytes_freed},
        )

    def clean_logs(self) -> OptimizationResult:
        """Clean old log files"""
        log_targets = [t for t in self.TARGETS if "log" in t.name.lower()]
        total_freed = 0
        total_deleted = 0

        for target in log_targets:
            result = self._clean_target(target)
            total_freed += result.bytes_freed
            total_deleted += result.files_deleted
            self._results.append(result)

        return OptimizationResult(
            success=True,
            module="cleanup",
            operation="cleanup_logs",
            message=f"Cleaned {total_deleted} log files, freed {total_freed / (1024*1024):.1f} MB",
            details={"files_deleted": total_deleted, "bytes_freed": total_freed},
        )

    def clean_thumbnails(self) -> OptimizationResult:
        """Clean thumbnail cache"""
        target = next((t for t in self.TARGETS if t.name == "thumbnail_cache"), None)
        if not target:
            return OptimizationResult(
                success=False,
                module="cleanup",
                operation="cleanup_thumbnails",
                message="Thumbnail cache target not found",
            )

        result = self._clean_target(target)
        self._results.append(result)

        return OptimizationResult(
            success=True,
            module="cleanup",
            operation="cleanup_thumbnails",
            message=f"Cleaned thumbnail cache, freed {result.bytes_freed / (1024*1024):.1f} MB",
            details={"files_deleted": result.files_deleted, "bytes_freed": result.bytes_freed},
        )

    def run_disk_cleanup(self, drive: str = "C:") -> OptimizationResult:
        """Run Windows Disk Cleanup utility"""
        try:
            # Set up cleanmgr to use sageset profile
            # This requires pre-configuration or admin to set options
            if not self.dry_run:
                guarded_run(
                    ["cleanmgr", "/d", drive, "/LOWDISK"],
                    timeout=600,
                )

            return OptimizationResult(
                success=True,
                module="cleanup",
                operation="disk_cleanup",
                message=f"Disk Cleanup completed for {drive}",
            )
        except Exception as e:
            return OptimizationResult(
                success=False,
                module="cleanup",
                operation="disk_cleanup",
                message=f"Failed: {e}",
            )

    def get_summary(self) -> dict[str, Any]:
        """Get summary of cleanup operations"""
        total_freed = sum(r.bytes_freed for r in self._results)
        total_deleted = sum(r.files_deleted for r in self._results)
        total_errors = sum(len(r.errors) for r in self._results)

        return {
            "total_files_deleted": total_deleted,
            "total_bytes_freed": total_freed,
            "total_mb_freed": round(total_freed / (1024 * 1024), 2),
            "total_errors": total_errors,
            "targets_cleaned": len(self._results),
            "results": [
                {
                    "target": r.target,
                    "files_deleted": r.files_deleted,
                    "mb_freed": round(r.bytes_freed / (1024 * 1024), 2),
                    "errors": len(r.errors),
                }
                for r in self._results
            ],
        }
