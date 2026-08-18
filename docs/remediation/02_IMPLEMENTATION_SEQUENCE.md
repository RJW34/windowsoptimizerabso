# 02 — Implementation Sequence

The sequence is safety-first. Do not expose repaired mutation code before containment and transaction layers are ready.

## Phase 0 — Baseline, containment, and ledger

- Verify Git HEAD against `BASELINE.json`.
- Run `tools/static_baseline_audit.py`.
- Reproduce compile/import failures.
- Create `docs/remediation/WORK_LEDGER.md`.
- Add a global mutation kill switch defaulting to read-only.
- Make legacy shortcut mutation commands unavailable or fail closed.
- Replace fake rollback output with an honest hard failure until real rollback lands.
- Add a repository warning indicating pre-alpha/not safe for host execution.
- Create a remediation branch and baseline commit.

**Exit:** No accessible command can mutate a machine; baseline artifacts and the full work ledger exist.

## Phase 1 — Runnability, package correctness, truthful CLI

- Fix syntax errors.
- Migrate to `src/windowsoptimizerabso`.
- Repair system-info collection and output.
- Reject invalid levels/options rather than silently choosing defaults.
- Establish deterministic exit codes.
- Add read-only `inspect`, `profiles list`, `history`, and `doctor`.
- Remove/correct nonexistent commands and README claims.
- Reconcile dependencies and build metadata.
- Add compile, import, wheel, install, and CLI-help tests.

**Exit:** Package builds and installs; read-only commands work safely on Windows and non-Windows; mutation remains disabled.

## Phase 2 — Typed domain, fake backends, planner

- Implement typed operation, state, plan, profile, result, and error models.
- Implement complete fake backends.
- Implement capability/applicability inspection.
- Implement conflict/dependency analysis.
- Implement immutable plan serialization, schema versioning, and digest.
- Implement active-user SID modeling.
- Port legacy analyses into truthful state inspectors.
- Add planner tests and golden snapshots.

**Exit:** Deterministic plans against fake machines; unsupported and not-applicable states are correct; profiles cannot inject arbitrary targets.

## Phase 3 — Durable journal and executor

- Implement durable, versioned transaction storage.
- Add process-wide lock.
- Make pre-state durable before apply.
- Add drift detection.
- Add privilege validation and constrained elevation.
- Add trusted subprocess wrapper.
- Implement apply/verify/rollback lifecycle.
- Add crash recovery and incomplete-transaction discovery.
- Add structured status/exit mapping.
- Inject faults before and after each lifecycle transition.

**Exit:** Fault injection proves recovery and reverse-order rollback; binary state round-trips; concurrent apply is safe.

## Phase 4 — Backends and module remediation

Port one operation at a time. Do not port broad legacy modules wholesale.

### Registry and identity

- exact type/existence/view/user capture
- read-back verification
- explicit target SID
- safe serialization and allowlists

### Files and cleanup

- canonical paths and reparse defense
- exact inventory and approval
- honest irreversibility
- browser profile discovery and lock handling
- remove prefetch/log “optimization” defaults unless strongly justified

### Services and scheduled tasks

- case-insensitive canonical identity
- exact state/config capture
- dependency/dependent checks
- transition waiting
- task XML/enabled-state restore
- no guessed default profile

### Power, network, gaming, visual

- capture exact current state
- remove unsupported commands and folklore
- retain only evidence-backed capability-gated operations
- split unrelated settings into separate IDs
- preserve OBS/capture and user preferences by default
- prefer session scope

**Exit:** Every retained operation has unit, fake contract, fault-injection, exact rollback, and Windows VM coverage. Removed operations have rationale.

## Phase 5 — Windows VM integration and reboot recovery

- Build disposable/snapshotted Windows validation environments.
- Test standard-user planning and administrator apply.
- Test intended interactive SID under alternate-admin elevation.
- Test registry, services, tasks, files, power, and retained network operations.
- Test apply → verify → reboot → verify → rollback → reboot → verify.
- Test missing feature, permission denial, timeout, interruption, disk full, journal corruption, and restore conflict.
- Capture before/after/rollback bundles.

**Exit:** Exact state equality after rollback is proven for all retained operations, allowing only documented benign nondeterministic metadata.

## Phase 6 — Product profiles and measurement

- Implement versioned profile schema.
- Add conservative Rivals of Aether 2 and Slippi profiles.
- Prefer session-scoped apply and automatic revert on game exit.
- Add crash/reboot recovery for abandoned sessions.
- Establish baseline and post-change performance measurement.
- Reject changes without target-workload benefit or acceptable tradeoff.
- Preserve streaming, capture, controller, audio, networking, and anti-cheat compatibility.

**Exit:** Profiles show understandable diffs, have no arbitrary targets, restore after normal/crash exit, and include evidence.

## Phase 7 — CI, documentation, security, release

- Add Windows and non-Windows CI.
- Add lint, typing, unit, contract, packaging, CLI, and security checks.
- Add dependency automation and scanning.
- Add accurate README, architecture, support matrix, risk catalog, troubleshooting, contribution, security, license, and changelog.
- Adopt honest pre-alpha/alpha versioning.
- Produce verifiable artifacts, checksums, and SBOM when ready.
- Document branch protection.

**Exit:** All blocking gates pass; docs match behavior; final proof bundle exists.

## Phase 8 — Independent final audit

Use `prompts/FINAL_AUDIT_PROMPT.txt` in a fresh context. Resolve every blocking finding before declaring completion.
