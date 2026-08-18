"""
Backup and restore functionality for safe optimization rollback
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from enum import Enum, auto

from loguru import logger

from ...safety import guard_mutation, guarded_run


class BackupType(Enum):
    """Types of backups"""
    REGISTRY = auto()
    SERVICE_CONFIG = auto()
    FILE = auto()
    SCHEDULED_TASK = auto()
    SYSTEM_RESTORE = auto()
    FULL_STATE = auto()


@dataclass
class BackupEntry:
    """A single backup entry"""
    id: str
    type: BackupType
    description: str
    path: Path
    created_at: datetime
    size_bytes: int
    metadata: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.name,
            "description": self.description,
            "path": str(self.path),
            "created_at": self.created_at.isoformat(),
            "size_bytes": self.size_bytes,
            "metadata": self.metadata,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupEntry:
        return cls(
            id=data["id"],
            type=BackupType[data["type"]],
            description=data["description"],
            path=Path(data["path"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            size_bytes=data["size_bytes"],
            metadata=data.get("metadata", {}),
            checksum=data.get("checksum", ""),
        )


@dataclass
class BackupSession:
    """A complete backup session (multiple entries from one operation)"""
    id: str
    created_at: datetime
    description: str
    entries: list[BackupEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "description": self.description,
            "entries": [e.to_dict() for e in self.entries],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupSession:
        return cls(
            id=data["id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            description=data["description"],
            entries=[BackupEntry.from_dict(e) for e in data["entries"]],
            metadata=data.get("metadata", {}),
        )


class BackupManager:
    """
    Manages system state backups for safe rollback.

    Features:
    - Registry key backup/restore
    - Service configuration snapshots
    - File backups
    - Scheduled task exports
    - Windows System Restore point creation
    - Full state snapshots
    """

    def __init__(self, backup_dir: Optional[Path] = None):
        self.backup_dir = backup_dir or Path.home() / ".winopt" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.registry_dir = self.backup_dir / "registry"
        self.services_dir = self.backup_dir / "services"
        self.files_dir = self.backup_dir / "files"
        self.tasks_dir = self.backup_dir / "tasks"

        # Create subdirectories
        for dir_path in [self.registry_dir, self.services_dir, self.files_dir, self.tasks_dir]:
            dir_path.mkdir(exist_ok=True)

        self.index_file = self.backup_dir / "index.json"
        self._sessions: list[BackupSession] = []
        self._load_index()

    def _load_index(self) -> None:
        """Load backup index from disk"""
        if self.index_file.exists():
            try:
                data = json.loads(self.index_file.read_text())
                self._sessions = [BackupSession.from_dict(s) for s in data.get("sessions", [])]
            except Exception as e:
                logger.error(f"Error loading backup index: {e}")
                self._sessions = []

    def _save_index(self) -> None:
        """Save backup index to disk"""
        data = {"sessions": [s.to_dict() for s in self._sessions]}
        self.index_file.write_text(json.dumps(data, indent=2))

    def _generate_id(self) -> str:
        """Generate unique backup ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hash_part = hashlib.md5(str(datetime.now().timestamp()).encode()).hexdigest()[:8]
        return f"{timestamp}_{hash_part}"

    def _calculate_checksum(self, path: Path) -> str:
        """Calculate file checksum"""
        if not path.exists():
            return ""

        md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5.update(chunk)
        return md5.hexdigest()

    def start_session(self, description: str) -> BackupSession:
        """Start a new backup session"""
        session = BackupSession(
            id=self._generate_id(),
            created_at=datetime.now(),
            description=description,
        )
        self._sessions.append(session)
        logger.info(f"Started backup session: {session.id}")
        return session

    def end_session(self, session: BackupSession) -> None:
        """Finalize and save a backup session"""
        session.metadata["entry_count"] = len(session.entries)
        session.metadata["total_size"] = sum(e.size_bytes for e in session.entries)
        self._save_index()
        logger.info(f"Completed backup session: {session.id} ({len(session.entries)} entries)")

    def backup_registry_key(
        self,
        session: BackupSession,
        key_path: str,
        description: str = "",
    ) -> Optional[BackupEntry]:
        """
        Backup a registry key using reg.exe export.

        Args:
            session: Current backup session
            key_path: Full registry path (e.g., "HKLM\\SOFTWARE\\Microsoft")
            description: Human-readable description

        Returns:
            BackupEntry if successful, None otherwise
        """
        entry_id = self._generate_id()
        backup_path = self.registry_dir / f"{entry_id}.reg"

        try:
            # Use reg.exe to export
            result = guarded_run(
                ["reg", "export", key_path, str(backup_path), "/y"],
                timeout=60,
            )

            if result.timed_out:
                logger.error(f"Registry export timed out: {key_path}")
                return None

            if result.returncode != 0:
                logger.error(f"Registry export failed: {result.stderr}")
                return None

            entry = BackupEntry(
                id=entry_id,
                type=BackupType.REGISTRY,
                description=description or f"Registry: {key_path}",
                path=backup_path,
                created_at=datetime.now(),
                size_bytes=backup_path.stat().st_size,
                metadata={"key_path": key_path},
                checksum=self._calculate_checksum(backup_path),
            )

            session.entries.append(entry)
            logger.debug(f"Backed up registry key: {key_path}")
            return entry

        except Exception as e:
            logger.error(f"Error backing up registry: {e}")
            return None

    def restore_registry_key(self, entry: BackupEntry) -> bool:
        """Restore a registry key from backup"""
        if entry.type != BackupType.REGISTRY:
            logger.error("Entry is not a registry backup")
            return False

        if not entry.path.exists():
            logger.error(f"Backup file not found: {entry.path}")
            return False

        try:
            result = guarded_run(
                ["reg", "import", str(entry.path)],
                timeout=60,
            )

            if result.returncode != 0:
                logger.error(f"Registry import failed: {result.stderr}")
                return False

            logger.info(f"Restored registry: {entry.metadata.get('key_path', entry.description)}")
            return True

        except Exception as e:
            logger.error(f"Error restoring registry: {e}")
            return False

    def backup_service_config(
        self,
        session: BackupSession,
        service_name: str,
        description: str = "",
    ) -> Optional[BackupEntry]:
        """
        Backup a Windows service configuration.

        Uses sc.exe to capture service settings.
        """
        entry_id = self._generate_id()
        backup_path = self.services_dir / f"{entry_id}_{service_name}.json"

        try:
            # Get service configuration
            qc_result = guarded_run(
                ["sc", "qc", service_name],
                timeout=30,
            )

            # Get service status
            query_result = guarded_run(
                ["sc", "query", service_name],
                timeout=30,
            )

            # Parse and save
            config_data = {
                "service_name": service_name,
                "config_output": qc_result.stdout,
                "status_output": query_result.stdout,
                "backed_up_at": datetime.now().isoformat(),
            }

            # Parse start type from config
            for line in qc_result.stdout.splitlines():
                if "START_TYPE" in line:
                    config_data["start_type"] = line.strip()
                    break

            backup_path.write_text(json.dumps(config_data, indent=2))

            entry = BackupEntry(
                id=entry_id,
                type=BackupType.SERVICE_CONFIG,
                description=description or f"Service: {service_name}",
                path=backup_path,
                created_at=datetime.now(),
                size_bytes=backup_path.stat().st_size,
                metadata={"service_name": service_name, "config": config_data},
                checksum=self._calculate_checksum(backup_path),
            )

            session.entries.append(entry)
            logger.debug(f"Backed up service config: {service_name}")
            return entry

        except Exception as e:
            logger.error(f"Error backing up service {service_name}: {e}")
            return None

    def backup_file(
        self,
        session: BackupSession,
        file_path: Path,
        description: str = "",
    ) -> Optional[BackupEntry]:
        """Backup a single file"""
        if not file_path.exists():
            logger.warning(f"File not found for backup: {file_path}")
            return None

        entry_id = self._generate_id()
        backup_path = self.files_dir / f"{entry_id}_{file_path.name}"

        try:
            shutil.copy2(file_path, backup_path)

            entry = BackupEntry(
                id=entry_id,
                type=BackupType.FILE,
                description=description or f"File: {file_path.name}",
                path=backup_path,
                created_at=datetime.now(),
                size_bytes=backup_path.stat().st_size,
                metadata={"original_path": str(file_path)},
                checksum=self._calculate_checksum(backup_path),
            )

            session.entries.append(entry)
            logger.debug(f"Backed up file: {file_path}")
            return entry

        except Exception as e:
            logger.error(f"Error backing up file {file_path}: {e}")
            return None

    def restore_file(self, entry: BackupEntry) -> bool:
        """Restore a file from backup"""
        if entry.type != BackupType.FILE:
            logger.error("Entry is not a file backup")
            return False

        # BAK-007: Path("") is PosixPath("."), which is truthy, so the original guard never fired
        # and a backup with no recorded origin would have been restored over the working directory.
        original_str = entry.metadata.get("original_path", "")
        if not original_str:
            logger.error("Original path not found in backup metadata")
            return False
        original_path = Path(original_str)

        try:
            guard_mutation(f"restore file over {original_path}", legacy=True)

            # Create backup of current state first
            if original_path.exists():
                temp_backup = original_path.with_suffix(original_path.suffix + ".rollback")
                shutil.copy2(original_path, temp_backup)

            shutil.copy2(entry.path, original_path)
            logger.info(f"Restored file: {original_path}")
            return True

        except Exception as e:
            logger.error(f"Error restoring file: {e}")
            return False

    def backup_scheduled_task(
        self,
        session: BackupSession,
        task_name: str,
        description: str = "",
    ) -> Optional[BackupEntry]:
        """Backup a scheduled task definition"""
        entry_id = self._generate_id()
        safe_name = task_name.replace("\\", "_").replace("/", "_")
        backup_path = self.tasks_dir / f"{entry_id}_{safe_name}.xml"

        try:
            result = guarded_run(
                ["schtasks", "/Query", "/TN", task_name, "/XML"],
                timeout=30,
            )

            if result.returncode != 0:
                logger.error(f"Task export failed: {result.stderr}")
                return None

            backup_path.write_text(result.stdout)

            entry = BackupEntry(
                id=entry_id,
                type=BackupType.SCHEDULED_TASK,
                description=description or f"Task: {task_name}",
                path=backup_path,
                created_at=datetime.now(),
                size_bytes=backup_path.stat().st_size,
                metadata={"task_name": task_name},
                checksum=self._calculate_checksum(backup_path),
            )

            session.entries.append(entry)
            logger.debug(f"Backed up scheduled task: {task_name}")
            return entry

        except Exception as e:
            logger.error(f"Error backing up task {task_name}: {e}")
            return None

    def create_system_restore_point(self, description: str) -> bool:
        """
        Create a Windows System Restore point.

        Requires administrator privileges and System Protection enabled.
        """
        try:
            # SEC-002/BAK-011: the description used to be interpolated straight into a PowerShell
            # string, so a description containing a double quote could close the literal and append
            # arbitrary commands to an elevated shell. The description is now passed out of band in
            # the child environment and read as $env:..., so it never reaches a parser. Appending it
            # to the -Command argument instead would not be safe: PowerShell concatenates trailing
            # arguments into the command text rather than binding them as parameters.
            if not description or len(description) > 255 or any(c in description for c in "\r\n\0"):
                logger.error("Restore point description is empty, too long, or contains newlines")
                return False

            script = (
                "Checkpoint-Computer "
                "-Description $env:WINOPT_RESTORE_POINT_DESCRIPTION "
                "-RestorePointType 'MODIFY_SETTINGS'"
            )
            result = guarded_run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command", script,
                ],
                timeout=120,
                extra_env={"WINOPT_RESTORE_POINT_DESCRIPTION": description},
            )

            if result.returncode == 0:
                logger.info(f"Created system restore point: {description}")
                return True
            else:
                logger.error(f"Failed to create restore point: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error creating restore point: {e}")
            return False

    def list_sessions(self) -> list[BackupSession]:
        """Get all backup sessions"""
        return sorted(self._sessions, key=lambda s: s.created_at, reverse=True)

    def get_session(self, session_id: str) -> Optional[BackupSession]:
        """Get a specific session by ID"""
        return next((s for s in self._sessions if s.id == session_id), None)

    def delete_session(self, session_id: str) -> bool:
        """Delete a backup session and its files"""
        session = self.get_session(session_id)
        if not session:
            return False

        # Delete files
        for entry in session.entries:
            try:
                if entry.path.exists():
                    entry.path.unlink()
            except Exception as e:
                logger.warning(f"Could not delete backup file {entry.path}: {e}")

        # Remove from index
        self._sessions = [s for s in self._sessions if s.id != session_id]
        self._save_index()

        logger.info(f"Deleted backup session: {session_id}")
        return True

    def cleanup_old_backups(self, days: int = 30) -> int:
        """Remove backups older than specified days"""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)

        old_sessions = [s for s in self._sessions if s.created_at < cutoff]
        deleted = 0

        for session in old_sessions:
            if self.delete_session(session.id):
                deleted += 1

        logger.info(f"Cleaned up {deleted} old backup sessions")
        return deleted

    def get_total_size(self) -> int:
        """Get total size of all backups in bytes"""
        total = 0
        for session in self._sessions:
            for entry in session.entries:
                total += entry.size_bytes
        return total

    def restore_session(self, session_id: str) -> dict[str, bool]:
        """Restore all entries from a session"""
        session = self.get_session(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return {}

        results = {}
        for entry in session.entries:
            try:
                if entry.type == BackupType.REGISTRY:
                    results[entry.id] = self.restore_registry_key(entry)
                elif entry.type == BackupType.FILE:
                    results[entry.id] = self.restore_file(entry)
                else:
                    logger.warning(f"Restore not implemented for type: {entry.type}")
                    results[entry.id] = False
            except Exception as e:
                logger.error(f"Error restoring {entry.id}: {e}")
                results[entry.id] = False

        return results
