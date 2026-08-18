# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning is
[SemVer](https://semver.org/), and the project is deliberately below 0.1 while acceptance gates
remain open — see [`docs/remediation/STATUS_REPORT.md`](docs/remediation/STATUS_REPORT.md).

## [Unreleased]

Nothing yet.

## [0.0.1a1] — 2026-08-18

First honest version. The repository previously declared 1.0.0 with no tests, no CI, and a rollback
command that printed success without restoring anything.

### Removed

- **All mutating commands.** `optimize`, `gaming`, `privacy`, `cleanup` and `visual --preset` now
  refuse with exit code 13. They mutated with no exact pre-state capture, no transaction journal and
  no verified rollback (BASE-003, BASE-007, BASE-008).
- **`rollback`'s false success.** It printed "Rollback complete." having restored nothing
  (BASE-004). It refuses until it can restore captured state and verify the restoration.
- **GUI dependencies.** `customtkinter`, `Pillow` and `ttkthemes` were declared for a GUI that does
  not exist (PRD-005, PKG-006).
- **Unused runtime dependencies.** `pywin32`, `wmi`, `questionary`, `toml`, `packaging`, and the
  test tools that were listed as runtime requirements (PKG-003).
- **Fabricated documentation.** Every usage example in the README — `--gui`, `--optimize all`,
  `--module`, `--backup`, `--restore`, `--profile` — described commands that were never implemented.

### Added

- **Containment** (`safety.py`): default-deny host mutation on four independent axes, a guarded
  subprocess runner resolving system binaries under `%SystemRoot%` instead of `PATH`, and per-site
  guards on every registry, service and filesystem mutation.
- **Typed domain model**: tagged captured state that distinguishes "key absent" from "value absent"
  from "empty value"; canonical encoding that round-trips binary registry data; explicit risk
  ordering; a ten-value operation status model.
- **Immutable plans**: digest-bound, expiring, pinned to a machine and OS build, with parameters
  validated against a declared schema so a profile cannot widen what an operation touches.
- **Planner**: applicability evaluation, topological dependency ordering, conflict detection, and
  zero-change plans as a valid outcome.
- **Durable journal** (SQLite/WAL): pre-state committed and fsynced before any mutating call,
  journalled lifecycle transitions, digest-verified reads, and schema versioning.
- **Transactional executor**: drift detection, postcondition verification, reverse-order verified
  rollback, distinct partial and failed rollback states, residual-drift reporting, crash recovery,
  and a process lock preventing concurrent apply.
- **Deterministic fake machine** with fault injection, stricter than Windows on registry types,
  service case-sensitivity and dependency enforcement.
- **Read-only CLI**: `inspect`, `doctor`, `history`, `exit-codes`, `version`, and a documented,
  tested exit-code contract.
- **241 tests**, CI on Linux and Windows across Python 3.10 and 3.12, CodeQL, pip-audit, ruff, mypy,
  and a clean-environment wheel install check.
- **LICENSE, SECURITY.md, CONTRIBUTING.md**, and the full remediation register under
  `docs/remediation/`.

### Fixed

Highlights; the full mapping is in [`docs/remediation/WORK_LEDGER.md`](docs/remediation/WORK_LEDGER.md).

- `info` constructed an empty `SystemInfo()`, called a `get_summary()` that did not exist, and
  expected a schema `to_dict()` never produced (BASE-002).
- The session-path suffix condition was inverted, so any name ending in `.json` had a second `.json`
  appended and could never be found (BASE-005).
- `restore_file` guarded a missing original path with `if not Path(...)`, but `Path("")` is truthy,
  so a backup with no recorded origin would have been restored over the working directory (BAK-007).
- The system-restore-point description was interpolated into a PowerShell command string; it now
  travels in the child environment and never reaches a parser (SEC-002, BAK-011).
- Registry rollback captured the *target* value type rather than the original, so restoring a
  `REG_SZ` wrote back a `REG_DWORD` (REG-001).
- `REG_BINARY` state could not be serialised at all — and the failure surfaced at session-save time,
  after the mutation had happened (CORE-007).
- Risk was ranked by `list(Enum).index()`, so inserting a member silently re-ranked every task
  (CORE-017).
- Service name comparison was case-sensitive against a case-insensitive platform, so `diagtrack`
  bypassed a guard written for `DiagTrack` (SVC-001).
- Timestamps were naive and ambiguous across a DST boundary (SYS-004); reports leaked the hostname
  with no redaction contract (SYS-003); `wmi` was imported and never used (SYS-001).

### Known not done

No legacy operation has been ported, nothing has been proven on real Windows, and there are no
profiles or benchmarks. 78 register items remain open. See the status report.
