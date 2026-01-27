"""
Core optimization engine - orchestrates all optimization modules
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger


class OptimizationLevel(Enum):
    """Optimization aggressiveness levels"""
    SAFE = auto()      # Only safe, easily reversible changes
    MODERATE = auto()  # Balanced performance vs stability
    AGGRESSIVE = auto()  # Maximum performance, may affect features
    CUSTOM = auto()    # User-defined settings


class OptimizationCategory(Enum):
    """Categories of optimizations"""
    CLEANUP = "cleanup"
    PRIVACY = "privacy"
    SERVICES = "services"
    STARTUP = "startup"
    REGISTRY = "registry"
    NETWORK = "network"
    GAMING = "gaming"
    VISUAL = "visual"
    POWER = "power"


@dataclass
class OptimizationResult:
    """Result of an optimization operation"""
    success: bool
    module: str
    operation: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    rollback_data: Optional[dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "module": self.module,
            "operation": self.operation,
            "message": self.message,
            "details": self.details,
            "rollback_data": self.rollback_data,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class OptimizationTask:
    """A single optimization task"""
    name: str
    description: str
    category: OptimizationCategory
    level: OptimizationLevel
    execute: Callable[[], OptimizationResult]
    rollback: Optional[Callable[[dict], bool]] = None
    requires_admin: bool = True
    requires_reboot: bool = False
    enabled: bool = True


class OptimizationEngine:
    """
    Central engine that coordinates all optimization modules.

    Handles:
    - Module registration and discovery
    - Execution ordering and dependencies
    - Backup creation before changes
    - Rollback coordination
    - Progress tracking and reporting
    """

    def __init__(
        self,
        level: OptimizationLevel = OptimizationLevel.SAFE,
        dry_run: bool = False,
        backup_dir: Optional[Path] = None,
    ):
        self.level = level
        self.dry_run = dry_run
        self.backup_dir = backup_dir or Path.home() / ".winopt" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self._modules: dict[str, Any] = {}
        self._tasks: list[OptimizationTask] = []
        self._results: list[OptimizationResult] = []
        self._callbacks: dict[str, list[Callable]] = {
            "on_task_start": [],
            "on_task_complete": [],
            "on_task_error": [],
            "on_progress": [],
        }

        logger.info(f"OptimizationEngine initialized (level={level.name}, dry_run={dry_run})")

    def register_module(self, name: str, module: Any) -> None:
        """Register an optimization module"""
        self._modules[name] = module
        logger.debug(f"Registered module: {name}")

        # Auto-discover tasks from module
        if hasattr(module, "get_tasks"):
            tasks = module.get_tasks()
            self._tasks.extend(tasks)
            logger.debug(f"Added {len(tasks)} tasks from {name}")

    def add_task(self, task: OptimizationTask) -> None:
        """Add a single optimization task"""
        self._tasks.append(task)

    def get_tasks(
        self,
        category: Optional[OptimizationCategory] = None,
        level: Optional[OptimizationLevel] = None,
    ) -> list[OptimizationTask]:
        """Get filtered list of tasks"""
        tasks = self._tasks

        if category:
            tasks = [t for t in tasks if t.category == category]

        if level:
            # Include tasks at or below the specified level
            level_order = list(OptimizationLevel)
            max_level_idx = level_order.index(level)
            tasks = [t for t in tasks if level_order.index(t.level) <= max_level_idx]

        return tasks

    def add_callback(self, event: str, callback: Callable) -> None:
        """Add event callback"""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _emit(self, event: str, *args, **kwargs) -> None:
        """Emit event to callbacks"""
        for callback in self._callbacks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Callback error for {event}: {e}")

    def analyze(self) -> dict[str, Any]:
        """
        Analyze system without making changes.
        Returns potential optimizations and their impact.
        """
        analysis = {
            "timestamp": datetime.now().isoformat(),
            "categories": {},
            "total_tasks": 0,
            "estimated_impact": {},
        }

        for category in OptimizationCategory:
            tasks = self.get_tasks(category=category, level=self.level)
            enabled_tasks = [t for t in tasks if t.enabled]

            analysis["categories"][category.value] = {
                "available_tasks": len(tasks),
                "enabled_tasks": len(enabled_tasks),
                "requires_reboot": any(t.requires_reboot for t in enabled_tasks),
                "tasks": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "level": t.level.name,
                        "requires_admin": t.requires_admin,
                    }
                    for t in enabled_tasks
                ],
            }
            analysis["total_tasks"] += len(enabled_tasks)

        return analysis

    def execute(
        self,
        categories: Optional[list[OptimizationCategory]] = None,
        task_names: Optional[list[str]] = None,
    ) -> list[OptimizationResult]:
        """
        Execute optimization tasks.

        Args:
            categories: Limit to specific categories
            task_names: Limit to specific task names

        Returns:
            List of optimization results
        """
        # Get applicable tasks
        tasks = self._tasks

        if categories:
            tasks = [t for t in tasks if t.category in categories]

        if task_names:
            tasks = [t for t in tasks if t.name in task_names]

        # Filter by level and enabled status
        tasks = [
            t for t in tasks
            if t.enabled and self._task_matches_level(t)
        ]

        logger.info(f"Executing {len(tasks)} optimization tasks")
        results = []

        for i, task in enumerate(tasks):
            self._emit("on_progress", i, len(tasks), task.name)
            self._emit("on_task_start", task)

            try:
                if self.dry_run:
                    result = OptimizationResult(
                        success=True,
                        module=task.category.value,
                        operation=task.name,
                        message=f"[DRY RUN] Would execute: {task.description}",
                    )
                else:
                    result = task.execute()

                results.append(result)
                self._emit("on_task_complete", task, result)

                if result.success:
                    logger.info(f"Completed: {task.name}")
                else:
                    logger.warning(f"Failed: {task.name} - {result.message}")

            except Exception as e:
                logger.error(f"Error executing {task.name}: {e}")
                result = OptimizationResult(
                    success=False,
                    module=task.category.value,
                    operation=task.name,
                    message=f"Error: {str(e)}",
                )
                results.append(result)
                self._emit("on_task_error", task, e)

        self._results.extend(results)
        self._emit("on_progress", len(tasks), len(tasks), "Complete")

        return results

    def _task_matches_level(self, task: OptimizationTask) -> bool:
        """Check if task matches current optimization level"""
        level_order = list(OptimizationLevel)
        task_idx = level_order.index(task.level)
        current_idx = level_order.index(self.level)
        return task_idx <= current_idx

    def rollback(self, result: OptimizationResult) -> bool:
        """Rollback a specific optimization"""
        if not result.rollback_data:
            logger.warning(f"No rollback data for {result.operation}")
            return False

        # Find the task
        task = next(
            (t for t in self._tasks if t.name == result.operation),
            None
        )

        if not task or not task.rollback:
            logger.warning(f"No rollback function for {result.operation}")
            return False

        try:
            return task.rollback(result.rollback_data)
        except Exception as e:
            logger.error(f"Rollback failed for {result.operation}: {e}")
            return False

    def rollback_all(self) -> dict[str, bool]:
        """Rollback all changes in reverse order"""
        results = {}
        for result in reversed(self._results):
            if result.rollback_data:
                results[result.operation] = self.rollback(result)
        return results

    def save_session(self, path: Optional[Path] = None) -> Path:
        """Save session results for later review/rollback"""
        if path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.backup_dir / f"session_{timestamp}.json"

        data = {
            "timestamp": datetime.now().isoformat(),
            "level": self.level.name,
            "dry_run": self.dry_run,
            "results": [r.to_dict() for r in self._results],
        }

        path.write_text(json.dumps(data, indent=2))
        logger.info(f"Session saved to {path}")
        return path

    def load_session(self, path: Path) -> list[OptimizationResult]:
        """Load a previous session"""
        data = json.loads(path.read_text())
        # Reconstruct results (rollback data preserved)
        results = []
        for r in data["results"]:
            results.append(OptimizationResult(
                success=r["success"],
                module=r["module"],
                operation=r["operation"],
                message=r["message"],
                details=r.get("details", {}),
                rollback_data=r.get("rollback_data"),
                timestamp=datetime.fromisoformat(r["timestamp"]),
            ))
        return results

    def get_summary(self) -> dict[str, Any]:
        """Get summary of executed optimizations"""
        successful = [r for r in self._results if r.success]
        failed = [r for r in self._results if not r.success]

        return {
            "total": len(self._results),
            "successful": len(successful),
            "failed": len(failed),
            "requires_reboot": any(
                t.requires_reboot
                for t in self._tasks
                if any(r.operation == t.name and r.success for r in self._results)
            ),
            "results": self._results,
        }
