# Windows Optimizer Absolute (WindowsOptimizerAbso)

> ## ⚠ PRE-ALPHA — mutation is disabled, and most of this tool does not exist yet
>
> An audit of the initial prototype found that its safety claims were substantially ahead of its
> implementation: `rollback` printed "Rollback complete." without restoring anything, mutating
> operations captured no exact pre-state, there was no transaction journal, no tests, and no CI.
>
> **Every command that changes a machine is currently withdrawn.** Read-only inspection works.
> What is implemented, what is quarantined and what is still owed is tracked in
> [`docs/remediation/WORK_LEDGER.md`](docs/remediation/WORK_LEDGER.md) against a register of 143
> known defects.
>
> Do not run this against a machine you care about. Use a disposable VM or Windows Sandbox.

## What this is meant to become

A per-game Windows state planner, rather than a universal "optimize everything" script. The
intended workflow is:

```text
inspect the machine
  → decide which operations are applicable to this build and hardware
  → select a versioned profile
  → produce a human-readable, immutable plan
  → capture exact pre-state and make it durable
  → apply one typed operation
  → verify the postcondition
  → keep it, or roll back to the captured state and verify the restoration
```

Rivals of Aether 2 and Slippi are the first intended profile targets. Product work comes after the
safety core: a tweak that cannot be exactly reverted has no business being offered.

## What works today

| Command | Status |
|---|---|
| `winopt inspect [--json] [--include-identifiers]` | Works. Read-only machine facts. |
| `winopt doctor [--json]` | Works. Reports environment readiness and containment state. |
| `winopt exit-codes [--json]` | Works. Documents the CLI contract. |
| `winopt version` | Works. |
| `winopt optimize` / `gaming` / `privacy` / `cleanup` / `visual` / `rollback` | **Withdrawn.** Exits 13 and explains why. |
| `winopt plan` / `apply` / `verify` / `recover` / `profiles` | **Not implemented yet.** Deliberately absent rather than stubbed. |

Inspection is unprivileged, works on non-Windows hosts (reporting what it could not collect), and
never writes anything.

## Install

```bash
git clone https://github.com/RJW34/windowsoptimizerabso.git
cd windowsoptimizerabso
python -m venv .venv
.venv\Scripts\activate          # PowerShell/cmd;  source .venv/bin/activate on Linux/macOS
pip install -e ".[dev]"
winopt doctor
```

Requires Python 3.10 or newer. Inspection and planning run unprivileged; applying a plan will
require administrator rights once apply exists.

## Exit codes

Automation can rely on these; they are tested in `tests/test_cli.py`. `winopt exit-codes` prints
the full table. The governing rule is that a command may not exit 0 unless it did what it said it
did — skipped, not-applicable, unverified and partial each get their own code.

| Code | Meaning |
|---:|---|
| 0 | success, or verified no-op |
| 2 | usage, input, or schema error |
| 3 | unsupported platform or capability |
| 5 | stale plan, machine state drifted |
| 7 | partial apply or verification failure |
| 9 | rollback partial or failed |
| 13 | refused: mutation disabled during remediation |

## Containment

While the transactional core is being built, host mutation is default-deny on four independent
axes, all of which must pass: `WINOPT_ALLOW_MUTATION` must be set, the platform must be Windows,
the quarantined prototype additionally requires `WINOPT_UNSAFE_LEGACY`, and any subprocess must
match a read-only allowlist. Anything unrecognised is treated as mutating.

Those variables exist so the legacy code can be exercised inside a disposable Windows VM during
porting. Setting them on a real machine gets you the unfixed prototype, which has no pre-state
capture, no journal, and no working rollback.

## Layout

```text
src/windowsoptimizerabso/
├── safety.py         # containment: the single choke point for any host mutation
├── cli/              # read-only commands and the exit-code contract
├── inspection/       # read-only machine facts
└── legacy/           # quarantined prototype: reference material, not a code path
docs/remediation/     # defect register, work ledger, decision log, target architecture
manifests/            # machine-readable defect and gate manifests
tests/                # containment, CLI and packaging proof
tools/                # static baseline audit
```

There is no GUI, no `config/`, no `scripts/`, and no registry-cleaner. The baseline README
advertised all of them.

## Development

```bash
pip install -e ".[dev]"
pytest                 # full suite
ruff check .           # lint (the legacy tree is excluded; see pyproject.toml)
python tools/static_baseline_audit.py --root . --output audit.json
```

## Status and history

- [`docs/remediation/WORK_LEDGER.md`](docs/remediation/WORK_LEDGER.md) — every known defect and its
  current disposition
- [`docs/remediation/DECISION_LOG.md`](docs/remediation/DECISION_LOG.md) — where this project
  deviates from the audit's prescription, and why (including one audit finding that did not
  reproduce)
- [`manifests/acceptance_gate_matrix.csv`](manifests/acceptance_gate_matrix.csv) — the blocking
  gates that must pass before any release

## Disclaimer

This software is designed to modify system settings. It is pre-alpha, it is not release-ready, and
several acceptance gates — including all Windows VM proof — remain open. Keep independent backups.

## License

MIT. See [LICENSE](LICENSE).
