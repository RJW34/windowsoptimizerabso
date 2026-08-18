# 03 — Test and Proof Plan

## Philosophy

This project changes operating-system state. Happy-path unit tests are insufficient. The suite must prove truthful status, exact pre-state capture, safe interruption, and exact rollback.

## 1. Static and package tests

Required:

```text
compile all Python files
import every public module
build wheel and source distribution
install wheel in a clean virtual environment
run console entry point
render CLI help
validate JSON schemas
scan for placeholder metadata and forbidden direct mutators
```

The build fails when source does not parse or documentation advertises a nonexistent command.

## 2. Domain-model tests

Cover:

- JSON round trips for every state type
- binary registry values
- absent key versus absent value versus present empty value
- timezone-aware timestamps
- schema rejection and migration
- plan digest stability
- plan expiry
- active user SID
- outcome/exit mapping
- redaction

## 3. Fake-backend contract tests

Every fake can:

- return normal state
- return missing feature
- deny permission
- time out
- change state between inspect and apply
- partially apply
- fail verification
- fail rollback
- produce locale/Unicode output
- simulate reboot-required state
- simulate disk full and journal write failure

Run the same operation lifecycle contract against every operation.

## 4. Lifecycle fault injection

Inject failure:

```text
before pre-state capture
during pre-state capture
after capture but before durable commit
after durable commit but before apply
during apply
after apply before verification
during verification
after verification before transaction commit
during rollback
after rollback before rollback verification
during rollback verification
```

For each, assert:

- journal state is truthful
- no uncaptured mutation occurred
- recovery identifies the next safe action
- rollback order is correct
- residual drift is reported
- exit code is nonzero where appropriate

## 5. Idempotency and conflict tests

- Same unchanged machine produces the same semantic plan.
- Already-satisfied operations are verified no-ops.
- Reapplying a committed plan is rejected or safely idempotent by policy.
- Repeated rollback does not corrupt state.
- Concurrent apply attempts are serialized or rejected.
- State drift forces re-plan.
- Conflicting profiles are rejected before mutation.

## 6. CLI tests

Test:

- command names/options
- invalid enums/profiles
- non-Windows behavior
- standard-user behavior
- confirmation digest
- JSON and human output
- all exit codes
- cancellation
- automation safety
- false-success prevention
- history/recovery output
- every documentation example

## 7. Path and filesystem security tests

On Windows test:

- junctions, symlinks, reparse points
- long and Unicode paths
- alternate data streams where relevant
- mixed case
- locked files
- files changing during plan/apply
- ACL denial
- destination collisions
- low disk space
- browser profiles beyond `Default`

No cleanup operation may escape its canonical approved root.

## 8. Windows VM integration

For each retained operation:

1. snapshot VM
2. capture baseline
3. create plan as standard user
4. review plan artifact
5. apply through privileged executor
6. verify immediately
7. reboot/logoff/restart Explorer when required
8. verify again
9. introduce unrelated later change where conflict handling matters
10. roll back
11. verify exact restoration or explicit conflict
12. reboot again when relevant
13. verify final state
14. restore VM snapshot

Never run destructive validation on the normal host.

## 9. Performance evidence

A registry change is not proof of optimization. For Rivals 2 and Slippi capture relevant metrics:

- frame-time distribution
- 1% and 0.1% lows
- input-to-present latency when instrumentable
- CPU/GPU utilization and clocks
- DPC/ISR latency where relevant
- network latency/jitter/loss for online workloads
- shader/stutter events
- power and temperature
- OBS/capture stability

Use repeated trials, warm-up, controlled background load, and a defined regression budget. Retain a setting only when evidence supports it or it is explicitly a user preference.

## Proof artifact layout

```text
artifacts/remediation-proof/
├── manifest.json
├── environment/
├── static/
├── unit/
├── contract/
├── fault-injection/
├── cli/
├── package/
├── windows-vm/
│   ├── machine-manifest.json
│   ├── before/
│   ├── after/
│   ├── after-reboot/
│   ├── rollback/
│   └── rollback-after-reboot/
├── benchmarks/
├── defect-dispositions.json
└── residual-risks.json
```

Every artifact must be reproducible by a documented command.

## Minimum thresholds

- 100% coverage of operation apply/verify/rollback branches by contract or integration tests.
- At least 90% branch coverage for planner, transaction, journal, executor, and state codecs.
- At least 80% branch coverage overall, with exclusions justified.
- Zero skipped blocking tests in release validation.
- Zero unhandled static type errors.
- Zero parse failures.
- Zero known false-success paths.
