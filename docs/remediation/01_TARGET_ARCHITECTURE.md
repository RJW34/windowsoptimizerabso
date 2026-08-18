# 01 — Target Architecture

## Objective

Separate inspection, planning, approval, privileged execution, verification, journaling, rollback, and reporting. The legacy design merges these concerns inside module methods and CLI shortcuts; the repaired design must make unsafe states difficult to represent.

## Recommended package layout

Migrate away from a top-level package literally named `src`:

```text
src/
└── windowsoptimizerabso/
    ├── __init__.py
    ├── cli/
    │   ├── app.py
    │   ├── commands_inspect.py
    │   ├── commands_plan.py
    │   ├── commands_apply.py
    │   ├── commands_rollback.py
    │   └── rendering.py
    ├── domain/
    │   ├── enums.py
    │   ├── operation.py
    │   ├── plan.py
    │   ├── state.py
    │   ├── transaction.py
    │   ├── profile.py
    │   └── errors.py
    ├── planner/
    │   ├── planner.py
    │   ├── applicability.py
    │   ├── conflict_detection.py
    │   └── plan_digest.py
    ├── executor/
    │   ├── executor.py
    │   ├── recovery.py
    │   ├── lock.py
    │   └── elevation.py
    ├── journal/
    │   ├── repository.py
    │   ├── sqlite_repository.py
    │   ├── codecs.py
    │   └── migrations/
    ├── backends/
    │   ├── protocols.py
    │   ├── fake/
    │   └── windows/
    │       ├── registry.py
    │       ├── services.py
    │       ├── scheduled_tasks.py
    │       ├── files.py
    │       ├── power.py
    │       ├── network.py
    │       ├── process.py
    │       ├── identity.py
    │       └── system_info.py
    ├── operations/
    │   ├── cleanup/
    │   ├── privacy/
    │   ├── startup/
    │   ├── services/
    │   ├── network/
    │   ├── gaming/
    │   └── visual/
    ├── profiles/
    │   ├── loader.py
    │   ├── schema.py
    │   └── builtins/
    ├── evidence/
    ├── reporting/
    └── util/
```

A different structure is acceptable only if it enforces the same boundaries.

## Core domain model

### `OperationSpec`

Every mutating capability must be represented by a typed definition containing at least:

- stable operation ID and schema version
- category, human-readable explanation, and risk
- scope: user / machine / file / process / session
- explicit target user SID when user-scoped
- supported OS editions, builds, architectures, hardware, and drivers
- admin and reboot/logoff/Explorer-restart requirements
- applicability inspector
- current-state capture
- desired-state representation
- apply implementation
- postcondition verifier
- rollback implementation and rollback verifier
- evidence record
- conflict keys and dependencies
- idempotency behavior
- session-scoped versus persistent behavior

An operation may not accept arbitrary registry paths, service names, shell strings, or deletion roots from an untrusted profile.

### `CapturedState`

Use explicit tagged types. Registry state must distinguish:

- key absent
- key present, value absent
- value present
- hive, subkey, value name
- WOW64 view
- exact registry type
- exact data, including safely encoded binary data
- target user SID and security context
- security metadata when relevant

Never use `None` alone to mean “did not exist.”

### `ExecutionPlan`

An immutable plan contains:

- plan ID and schema version
- timezone-aware timestamp
- redacted machine fingerprint
- active user identity
- source profile ID/version
- ordered operations
- captured planning state and desired state
- risk/tradeoff summaries
- conflict analysis
- reboot/logoff effects
- plan digest
- expiry/drift policy

The apply command rejects a plan when relevant current state changed.

### `TransactionJournal`

Use a durable store with schema versioning and migrations. SQLite in WAL mode is recommended. The journal is recovery state, not a final summary.

Persist operation transitions such as:

```text
PLANNED
PRESTATE_CAPTURED
PRESTATE_DURABLE
APPLY_STARTED
APPLY_RETURNED
POSTSTATE_VERIFIED
COMMITTED
ROLLBACK_STARTED
ROLLBACK_RETURNED
ROLLBACK_VERIFIED
```

Transaction states must distinguish:

```text
PREPARED
RUNNING
SUCCEEDED
PARTIAL
FAILED
ROLLBACK_PENDING
ROLLING_BACK
ROLLED_BACK
ROLLBACK_PARTIAL
ROLLBACK_FAILED
REBOOT_PENDING
RECOVERY_REQUIRED
```

Durably commit pre-state before calling a mutating backend.

### `Outcome`

Do not use one boolean. Capture:

- status
- operation ID
- timestamps
- changed or no-op
- applicability
- observed pre-state and post-state
- verification details
- structured error category
- sanitized diagnostics
- reboot/logoff effect
- rollback availability
- residual drift

## Backend protocols

The planner and tests operate against interfaces:

- `RegistryBackend`
- `ServiceBackend`
- `ScheduledTaskBackend`
- `FileBackend`
- `PowerBackend`
- `NetworkBackend`
- `ProcessBackend`
- `IdentityBackend`
- `SystemInfoBackend`

Provide complete deterministic fakes with fault injection.

Windows implementations must:

- resolve trusted system binaries by absolute path
- avoid `shell=True`
- use typed arguments
- constrain environment and working directory
- capture return code, stdout, stderr, timeout, and encoding
- distinguish missing capability from failure
- avoid locale-dependent parsing when possible
- protect against reparse points and traversal
- read back state after every write

## Planner and executor separation

The unprivileged planner inspects and creates plans. It does not mutate.

The privileged executor receives only:

- a serialized immutable plan
- plan digest
- confirmation token
- allowlisted operation registry

It validates schema, digest, machine, target user, freshness, and state drift. It never receives arbitrary scripts or commands.

## Rollback semantics

Rollback means exact restoration of captured state, not guessed defaults.

1. Restore only operations that crossed the apply boundary.
2. Restore in reverse order.
3. Verify every restore.
4. Preserve unrelated later changes; detect conflict rather than clobbering.
5. Report residual drift.
6. Make repeated rollback safe.
7. Support crash recovery from the journal.
8. If exact rollback is impossible, the operation cannot be presented as safely reversible.

## Profiles

Profiles select allowlisted operation IDs plus constrained parameters. They contain no code, arbitrary shell, registry paths, service names, or deletion roots.

Profiles include:

- ID and version
- product/game
- scope and session behavior
- supported environment
- operation selections
- conflict policy
- evidence references
- expected metrics
- rollback policy

Validate against a strict schema and reject unknown fields.

## Compatibility

Legacy CLI aliases may remain temporarily only if they route through the new plan/apply lifecycle. No alias may call a mutator directly.
