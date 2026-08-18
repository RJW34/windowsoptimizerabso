# 00 — Current State and Mission

## Baseline summary

The repository is a single-commit Python prototype that advertises a comprehensive Windows optimizer but fails before the CLI can load. The code contains useful domain ideas—registry wrappers, service helpers, optimization tasks, backup entries, and CLI commands—but the safety claims are substantially ahead of the implementation.

The goal is not to preserve every legacy tweak. Preserve valid product intent while replacing unsafe or unsupported implementation choices.

## Immediate reproducible blockers

Claude must reproduce these against the pinned baseline before changing code:

1. `src/modules/cleanup.py` has invalid `C:\` string literals in the `cleanmgr` command and `run_disk_cleanup` default argument. Importing `src.main` therefore fails.
2. `info` constructs `SystemInfo()` instead of calling `SystemInfo.gather()`, calls a nonexistent `get_summary()`, and expects a schema that `to_dict()` does not provide.
3. General `optimize` calls nonexistent `BackupManager.create_system_backup()`.
4. `rollback` performs no rollback and prints `Rollback complete`.
5. Session-path handling can append `.json` incorrectly.
6. Loaded session results are not connected to engine rollback state.
7. `gaming`, `privacy`, and `cleanup` shortcuts bypass backup and session persistence.
8. `visual --preset` mutates directly with no central plan, journal, confirmation, or rollback record.
9. `OptimizationResult` dynamically receives `requires_reboot`, but the field is not declared or serialized.
10. Binary registry state can enter rollback data, but raw `bytes` cannot be serialized by the current JSON session writer.
11. No tests, CI workflows, release tags, release artifacts, or protected-branch gates exist.
12. README commands, directories, GUI claims, backup claims, rollback claims, service-profile claims, and registry-cleanup claims do not match the repository.

## Safety classification

The current commit is:

- not importable
- not suitable for administrator execution
- not transaction-safe
- not exactly reversible
- not truthful about rollback
- not evidence-based
- not release-ready

The first code change should make mutation impossible until the new safety core is ready. Repairing syntax alone would expose unsafe shortcut commands and is therefore not a sufficient first phase.

## Intended product direction

The strongest product direction is a measured, per-game Windows state planner rather than a universal “optimize everything” script.

A valid workflow is:

```text
inspect current machine
→ determine applicability
→ select a versioned profile
→ produce a human-readable immutable plan
→ capture exact pre-state
→ apply one typed operation
→ verify the postcondition
→ benchmark where relevant
→ keep or roll back
→ restore session-scoped settings when the target game exits
```

Rivals of Aether 2 and Slippi are the first profile targets, but product work comes after the safety core.

## Legacy code disposition rule

Each existing operation receives one explicit disposition:

- **Retain and repair:** supported, useful, and fully reversible.
- **Redesign:** intent valid, implementation or scope unsafe.
- **Quarantine as experimental:** evidence inconclusive; opt-in only.
- **Remove:** unsupported, misleading, obsolete, dangerous, or not an optimization.

No operation remains merely because it already exists.
