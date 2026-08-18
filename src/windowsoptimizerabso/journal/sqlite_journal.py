"""Durable transaction journal.

The journal is *recovery state*, not a report. Its job is to make this true: if the process dies at
any point, what survives on disk is enough to work out whether the machine was touched and to put
it back.

That drives three design choices the baseline's JSON session file could not meet:

- **Pre-state is committed before the mutating call, not after.** A session file written at the end
  of a run records nothing about a run that crashed in the middle -- which is precisely the run
  that needs recovering.
- **Durability is checkpointed, not assumed.** A committed SQLite transaction in WAL mode survives
  process death, but the WAL is not necessarily on the platter until it is checkpointed. Power loss
  mid-apply is the exact scenario rollback exists for, so ``mark_prestate_durable`` checkpoints and
  fsyncs before the executor is allowed to proceed (DECISION_LOG D-004).
- **Stored state is digest-verified on read.** A journal that silently returns corrupted pre-state
  is worse than one that refuses to roll back, because the corrupted value gets written over a live
  machine.

The baseline's index file was also written non-atomically, so an interrupted write turned the whole
backup history into an empty file (defect BAK-006). Every write here is a single SQLite
transaction.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..domain import codecs
from ..domain.enums import LifecyclePhase, OperationStatus, TransactionState
from ..domain.state import StateSet

#: Journal schema version. A journal written by a newer build is refused rather than half-read:
#: guessing at an unknown schema risks mis-reading a pre-state blob.
JOURNAL_SCHEMA_VERSION = 1


class JournalError(RuntimeError):
    """The journal could not be read, written, or trusted."""


class JournalCorruption(JournalError):
    """Stored data failed its integrity check. Never repaired silently."""


@dataclass(frozen=True)
class TransactionRecord:
    transaction_id: str
    plan_id: str
    plan_digest: str
    machine_fingerprint: str
    state: TransactionState
    created_at: datetime
    updated_at: datetime

    @property
    def needs_recovery(self) -> bool:
        return self.state.needs_recovery


@dataclass(frozen=True)
class OperationRecord:
    transaction_id: str
    sequence: int
    operation_id: str
    phase: LifecyclePhase
    status: OperationStatus | None
    prestate: StateSet | None
    error_category: str | None
    detail: str

    @property
    def may_have_mutated(self) -> bool:
        """Whether recovery must assume the machine was touched.

        True from ``APPLY_STARTED`` onwards: the process can die between the mutating call
        returning and the journal write, so "no result recorded" does not mean "nothing happened".
        """
        return self.phase.crossed_apply_boundary


_SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id      TEXT PRIMARY KEY,
    plan_id             TEXT NOT NULL,
    plan_digest         TEXT NOT NULL,
    machine_fingerprint TEXT NOT NULL,
    state               TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations (
    transaction_id  TEXT NOT NULL,
    sequence        INTEGER NOT NULL,
    operation_id    TEXT NOT NULL,
    phase           TEXT NOT NULL,
    status          TEXT,
    prestate_blob   TEXT,
    prestate_digest TEXT,
    error_category  TEXT,
    detail          TEXT NOT NULL DEFAULT '',
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (transaction_id, sequence),
    FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id)
);

-- Append-only history. `operations` holds the current phase; this holds how it got there, which
-- is what makes a post-mortem possible after a crash.
CREATE TABLE IF NOT EXISTS events (
    event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT NOT NULL,
    sequence       INTEGER,
    phase          TEXT,
    state          TEXT,
    detail         TEXT NOT NULL DEFAULT '',
    recorded_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_state ON transactions(state);
CREATE INDEX IF NOT EXISTS idx_events_transaction ON events(transaction_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteJournal:
    """SQLite-backed journal. One instance per process; safe to reopen after a crash."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, isolation_level=None, timeout=30.0)
        self._connection.row_factory = sqlite3.Row
        self._configure()
        self._migrate()

    def _configure(self) -> None:
        cursor = self._connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        # FULL, not NORMAL: NORMAL lets the WAL sync lazily, which is exactly the window in which
        # a power loss would lose the pre-state of a mutation that already happened.
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.execute("PRAGMA foreign_keys=ON")

    def _migrate(self) -> None:
        # executescript issues an implicit COMMIT before running, so it cannot be nested inside an
        # explicit transaction. The DDL is idempotent (every statement is IF NOT EXISTS), so it is
        # safe to run outside one; the version check that follows is not, and is.
        self._connection.executescript(_SCHEMA)
        with self.transaction() as cursor:
            row = cursor.execute(
                "SELECT value FROM journal_meta WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                cursor.execute(
                    "INSERT INTO journal_meta(key, value) VALUES('schema_version', ?)",
                    (str(JOURNAL_SCHEMA_VERSION),),
                )
                return
            stored = int(row["value"])
            if stored > JOURNAL_SCHEMA_VERSION:
                raise JournalError(
                    f"journal at {self.path} uses schema version {stored}; this build understands "
                    f"{JOURNAL_SCHEMA_VERSION}. Refusing to read it rather than risk mis-reading "
                    "captured state."
                )
            # Older versions would be migrated here. Version 1 is the first.

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Cursor]:
        """One atomic unit. Either the whole journal update lands or none of it does (BAK-006)."""
        cursor = self._connection.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            yield cursor
        except BaseException:
            cursor.execute("ROLLBACK")
            raise
        cursor.execute("COMMIT")

    def close(self) -> None:
        self._connection.close()

    # -- transactions ------------------------------------------------------

    def begin_transaction(self, *, plan_id: str, plan_digest: str, machine_fingerprint: str) -> str:
        transaction_id = f"txn-{uuid.uuid4().hex[:12]}"
        stamp = _now()
        with self.transaction() as cursor:
            cursor.execute(
                "INSERT INTO transactions(transaction_id, plan_id, plan_digest, "
                "machine_fingerprint, state, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (transaction_id, plan_id, plan_digest, machine_fingerprint,
                 TransactionState.PREPARED.value, stamp, stamp),
            )
            self._append_event(cursor, transaction_id, None, None,
                               TransactionState.PREPARED, "transaction prepared")
        return transaction_id

    def set_transaction_state(
        self, transaction_id: str, state: TransactionState, detail: str = ""
    ) -> None:
        with self.transaction() as cursor:
            updated = cursor.execute(
                "UPDATE transactions SET state=?, updated_at=? WHERE transaction_id=?",
                (state.value, _now(), transaction_id),
            ).rowcount
            if updated == 0:
                raise JournalError(f"unknown transaction {transaction_id}")
            self._append_event(cursor, transaction_id, None, None, state, detail)

    def get_transaction(self, transaction_id: str) -> TransactionRecord:
        row = self._connection.execute(
            "SELECT * FROM transactions WHERE transaction_id=?", (transaction_id,)
        ).fetchone()
        if row is None:
            raise JournalError(f"unknown transaction {transaction_id}")
        return self._to_transaction(row)

    def list_transactions(self, limit: int = 50) -> tuple[TransactionRecord, ...]:
        rows = self._connection.execute(
            "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return tuple(self._to_transaction(r) for r in rows)

    def incomplete_transactions(self) -> tuple[TransactionRecord, ...]:
        """Transactions that were interrupted and still owe the machine something.

        This is what ``winopt recover`` reads on startup. A transaction left ``RUNNING`` means the
        process died mid-apply and the machine may hold an unrecorded change (defect CORE-011).
        """
        states = [s.value for s in TransactionState if s.needs_recovery]
        placeholders = ",".join("?" * len(states))
        rows = self._connection.execute(
            f"SELECT * FROM transactions WHERE state IN ({placeholders}) ORDER BY created_at",
            states,
        ).fetchall()
        return tuple(self._to_transaction(r) for r in rows)

    # -- operations --------------------------------------------------------

    def record_prestate(
        self,
        transaction_id: str,
        sequence: int,
        operation_id: str,
        prestate: StateSet,
    ) -> None:
        """Write captured pre-state. Must be followed by :meth:`mark_prestate_durable`."""
        blob = prestate.serialise()
        with self.transaction() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO operations(transaction_id, sequence, operation_id, phase, "
                "status, prestate_blob, prestate_digest, error_category, detail, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (transaction_id, sequence, operation_id, LifecyclePhase.PRESTATE_CAPTURED.value,
                 None, blob, codecs.digest(blob), None, "", _now()),
            )
            self._append_event(cursor, transaction_id, sequence,
                               LifecyclePhase.PRESTATE_CAPTURED, None, operation_id)

    def mark_prestate_durable(self, transaction_id: str, sequence: int) -> None:
        """Force the captured pre-state to stable storage before any mutation is attempted.

        Checkpoints the WAL and fsyncs the database file. Without this the pre-state is durable
        against process death but not against power loss, and power loss mid-apply is the case
        rollback exists for. See DECISION_LOG D-004 for the platform caveat: ``os.fsync`` maps to
        ``FlushFileBuffers`` on Windows, which some virtual disks acknowledge without flushing.
        """
        with self.transaction() as cursor:
            cursor.execute(
                "UPDATE operations SET phase=?, updated_at=? WHERE transaction_id=? AND sequence=?",
                (LifecyclePhase.PRESTATE_DURABLE.value, _now(), transaction_id, sequence),
            )
            self._append_event(cursor, transaction_id, sequence,
                               LifecyclePhase.PRESTATE_DURABLE, None, "")

        self._connection.execute("PRAGMA wal_checkpoint(FULL)")
        descriptor = os.open(self.path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def record_phase(
        self,
        transaction_id: str,
        sequence: int,
        phase: LifecyclePhase,
        *,
        status: OperationStatus | None = None,
        error_category: str | None = None,
        detail: str = "",
    ) -> None:
        with self.transaction() as cursor:
            updated = cursor.execute(
                "UPDATE operations SET phase=?, status=?, error_category=?, detail=?, updated_at=? "
                "WHERE transaction_id=? AND sequence=?",
                (phase.value, status.value if status else None, error_category, detail, _now(),
                 transaction_id, sequence),
            ).rowcount
            if updated == 0:
                raise JournalError(
                    f"no journalled operation {sequence} in {transaction_id}: pre-state must be "
                    "recorded before any phase transition"
                )
            self._append_event(cursor, transaction_id, sequence, phase, None, detail)

    def get_operations(self, transaction_id: str) -> tuple[OperationRecord, ...]:
        rows = self._connection.execute(
            "SELECT * FROM operations WHERE transaction_id=? ORDER BY sequence", (transaction_id,)
        ).fetchall()
        return tuple(self._to_operation(r) for r in rows)

    def get_prestate(self, transaction_id: str, sequence: int) -> StateSet:
        """Read captured pre-state, verifying its digest first.

        Raises :class:`JournalCorruption` rather than returning a best-effort value: this data is
        about to be written over a live machine.
        """
        row = self._connection.execute(
            "SELECT prestate_blob, prestate_digest FROM operations "
            "WHERE transaction_id=? AND sequence=?",
            (transaction_id, sequence),
        ).fetchone()
        if row is None or row["prestate_blob"] is None:
            raise JournalError(f"no pre-state recorded for {transaction_id}[{sequence}]")
        blob, stored_digest = row["prestate_blob"], row["prestate_digest"]
        if codecs.digest(blob) != stored_digest:
            raise JournalCorruption(
                f"pre-state for {transaction_id}[{sequence}] failed its integrity check. "
                "Refusing to restore from it: writing corrupted state over a live machine is worse "
                "than not rolling back."
            )
        return StateSet.deserialise(blob)

    def events(self, transaction_id: str) -> tuple[dict[str, Any], ...]:
        rows = self._connection.execute(
            "SELECT * FROM events WHERE transaction_id=? ORDER BY event_id", (transaction_id,)
        ).fetchall()
        return tuple(dict(r) for r in rows)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _append_event(
        cursor: sqlite3.Cursor,
        transaction_id: str,
        sequence: int | None,
        phase: LifecyclePhase | None,
        state: TransactionState | None,
        detail: str,
    ) -> None:
        cursor.execute(
            "INSERT INTO events(transaction_id, sequence, phase, state, detail, recorded_at) "
            "VALUES (?,?,?,?,?,?)",
            (transaction_id, sequence, phase.value if phase else None,
             state.value if state else None, detail, _now()),
        )

    @staticmethod
    def _to_transaction(row: sqlite3.Row) -> TransactionRecord:
        return TransactionRecord(
            transaction_id=row["transaction_id"],
            plan_id=row["plan_id"],
            plan_digest=row["plan_digest"],
            machine_fingerprint=row["machine_fingerprint"],
            state=TransactionState(row["state"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _to_operation(self, row: sqlite3.Row) -> OperationRecord:
        prestate = None
        if row["prestate_blob"] is not None:
            # Corruption is reported by `get_prestate` at the point of use, not here. Listing the
            # operations in a transaction must keep working when one blob is damaged, so that
            # rollback can restore the operations it still can and report the one it cannot,
            # rather than aborting the whole recovery.
            try:
                if codecs.digest(row["prestate_blob"]) == row["prestate_digest"]:
                    prestate = StateSet.deserialise(row["prestate_blob"])
            except codecs.DecodeError:
                prestate = None
        return OperationRecord(
            transaction_id=row["transaction_id"],
            sequence=row["sequence"],
            operation_id=row["operation_id"],
            phase=LifecyclePhase(row["phase"]),
            status=OperationStatus(row["status"]) if row["status"] else None,
            prestate=prestate,
            error_category=row["error_category"],
            detail=row["detail"] or "",
        )
