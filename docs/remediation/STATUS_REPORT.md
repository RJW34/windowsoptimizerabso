# Remediation Status Report

**Baseline:** `fed422ddc1b5808ad6c98908a96231a98b6ed625`
**Date:** 2026-08-18
**Version:** 0.0.1a1 — pre-alpha, **not release-ready**

This is a progress report, not the final report the pack's
[`10_FINAL_REPORT_TEMPLATE.md`](10_FINAL_REPORT_TEMPLATE.md) describes. That report cannot honestly
be written until the Windows VM gates pass, and this document says plainly which gates are still
open rather than declaring completion.

---

## Where the register stands

| Status | Count | Notes |
|---|---:|---|
| fixed | 58 | 25 critical, 27 high, 6 medium — each with a named passing test |
| removed | 2 | claim or dependency deleted rather than repaired |
| deferred | 4 | understood and sequenced, blocked on a disposable Windows VM |
| rejected | 1 | BASE-001 does not reproduce — see [`DECISION_LOG.md`](DECISION_LOG.md) D-001 |
| **open** | **78** | 27 critical, 45 high, 6 medium — mostly Phase 4 module remediation |

Row-level detail is in [`WORK_LEDGER.md`](WORK_LEDGER.md). Nothing is marked `fixed` on the strength
of a code change alone: the rule from `CLAUDE.md` is that a fix needs a passing test or a proof
artifact, and every `fixed` row names one.

## Acceptance gates

| Gate | State | Evidence / what remains |
|---|---|---|
| G0 Containment | **passing** | `tests/test_containment.py`, 53 tests. No reachable command can mutate a host. |
| G1 Build/package | **passing** | `tests/test_packaging.py`, `tests/test_cli.py`; wheel builds and installs clean; CI smoke-tests the entry point. |
| G2 Planner | **passing** | `tests/test_planner.py`, 29 tests. Typed allowlisted operations, digest-bound immutable plans, drift and conflict detection. |
| G3 Journal | **passing (fakes)** | `tests/test_executor.py`. Durable pre-state before apply, journalled transitions, locking, corruption handling, crash recovery. Not yet exercised against a real power-loss event. |
| G4 Verification/rollback | **passing (fakes)** | Whole-machine snapshot equality across apply and rollback, including `REG_BINARY` in a user hive, with faults injected at every boundary. |
| G5 Module remediation | **open** | Phase 4 has not started. No legacy operation has been ported yet. |
| G6 Windows VM | **open — blocked** | No Windows host available in this environment. See below. |
| G7 Security | **partial** | Privilege split, SID modelling, trusted subprocess resolution, redaction and locking are in place and tested. Reparse-point defence (SEC-004) arrives with the file backend in Phase 4. |
| G8 Testing | **partial** | 241 tests pass across containment, domain, planner, journal, executor, CLI and packaging. No coverage threshold is enforced yet, and the VM layer is absent. |
| G9 Profiles | **open** | Phase 6. No profile schema, no Rivals 2 or Slippi profile. |
| G10 CI/governance | **passing** | Linux+Windows CI, CodeQL, pip-audit, lint, types, packaging; LICENSE, SECURITY, CONTRIBUTING, CHANGELOG present; version is honestly pre-alpha. Branch protection is a repository setting, documented below but not applied from here. |
| G11 Final proof | **open** | Depends on G5, G6 and G9. |

## What was built

**Phase 0 — containment.** `safety.py` is the single choke point for host mutation, default-deny on
four independent axes. 38 subprocess call sites moved behind a guarded runner that resolves system
binaries under `%SystemRoot%` rather than `PATH`, never uses a shell, constrains the child
environment, and reports timeout distinctly from failure. `SafetyError` derives from
`BaseException` — found by testing, when the guard fired correctly inside a legacy service call and
the legacy `except Exception: return False` swallowed it and reported an ordinary failure.

**Phase 1 — package and CLI.** Package moved to `src/windowsoptimizerabso/` with the prototype
quarantined under `legacy/`. Read-only `inspect`, `doctor`, `history` and `exit-codes`; the six
mutating commands remain present and refuse with exit 13 and their defect IDs. Dependencies cut to
the four that are actually imported. README rewritten — every usage example in the baseline was
fabricated.

**Phase 2 — domain and planner.** Tagged captured state that records *how* a thing was missing;
canonical encoding that round-trips `REG_BINARY` (which `json.dumps` could not serialise at all, and
failed at save time after the mutation); immutable digest-bound plans that expire and are pinned to a
machine; a planner that evaluates applicability, orders dependencies and refuses conflicts; a
deterministic fake machine that is stricter than Windows on purpose.

**Phase 3 — journal and executor.** SQLite/WAL journal with checkpointed, fsynced pre-state durability
before any mutating call; a process lock that fails closed; and the
capture → drift-check → durable → apply → verify → commit lifecycle, with reverse-order verified
rollback, distinct partial and failed rollback states, residual-drift reporting, and crash recovery.

## What is not done, stated plainly

- **No legacy operation has been ported.** Every one of the gaming, network, privacy, cleanup,
  startup, services and visual operations is still the unfixed prototype behind two opt-ins. The
  81 open register items are overwhelmingly this work.
- **Nothing has been proven on Windows.** The lifecycle is proven against deterministic fakes. That
  is a real proof of the *logic* — reverse-order rollback, exact state equality, fault recovery —
  and it is not a proof that `winreg`, `sc.exe` or `schtasks.exe` behave as modelled. Registry view
  redirection, service transition timing, locale-dependent output and reparse points are all
  modelled from documentation, not observed.
- **The executor has no CLI surface.** `plan`, `apply`, `verify`, `rollback` and `recover` are
  implemented as a library and tested, but are deliberately not wired to commands until a real
  operation exists to run through them. Exposing an apply command with nothing safe to apply would
  be the same category of error as the baseline's rollback.
- **No profiles, no benchmarks.** Phase 6 in full.
- **Branch protection is not applied.** It is a repository setting, not a file. Recommended:
  require the `test`, `lint`, `package` and `containment` checks on `master`, require a review, and
  disallow force-push.

## Reproducing the validation

```bash
git clone https://github.com/RJW34/windowsoptimizerabso.git
cd windowsoptimizerabso
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest -q                                  # 241 tests
ruff check .                               # clean
mypy src/windowsoptimizerabso              # clean
python -m build                            # wheel + sdist

# Baseline audit the remediation is measured against
python tools/static_baseline_audit.py --root . --output audit.json

# Containment, on its own
pytest tests/test_containment.py -q

# The exact-rollback proof specifically
pytest tests/test_executor.py -q -k "rollback or recovery or drift"
```

The withdrawn commands can be confirmed to refuse without any risk, on any platform:

```bash
for c in optimize gaming privacy cleanup visual rollback; do winopt $c; echo "$c -> $?"; done
# each prints a refusal and exits 13
```

## Residual risk register

| Risk | Severity | Mitigation | Status |
|---|---|---|---|
| Windows behaviour differs from the model in the fakes | high | Backends are interfaces; fakes are stricter than Windows; contract tests will run against both | open until G6 |
| `os.fsync` not honoured by a virtual disk or consumer SSD | medium | Documented in SECURITY.md; cannot be fixed in user mode | accepted |
| A recycled PID makes a stale lock look live | low | Fails closed — the second executor refuses rather than racing | accepted |
| Machine fingerprint is a redaction, not an anonymisation | low | Documented; unsalted by design so reports correlate | accepted |
| Legacy tree still contains unfixed dangerous code | high | Unreachable from the CLI, guarded by two opt-ins, structurally tested | open until Phase 4 deletes it |
| No coverage threshold enforced | medium | 241 tests across every implemented layer; threshold to be set once Phase 4 lands | open |

## Recommended next work, in order

1. **Phase 4, one operation at a time.** Start with a Windows registry backend and port a single
   narrow, well-documented operation end to end — Game DVR is a reasonable first, since it is one
   setting with a primary source. Delete its legacy implementation in the same commit.
2. **Wire `plan` / `apply` / `verify` / `rollback` / `recover` to the CLI** once that one operation
   exists, with digest confirmation on apply.
3. **Stand up the disposable Windows VM harness** and run the apply → reboot → verify → rollback →
   reboot equality proof for that operation. That closes G6 for one operation and establishes the
   pattern for the rest.
4. **Then the folklore triage.** The gaming, network and visual modules are where most of the
   remaining critical items are, and most of them will end in `remove`, not `fix` — GAM-002 through
   GAM-004, NET-001 through NET-003 and NET-006/007, VIS-002 and VIS-003 are all listed as
   `remove` in the register's own default disposition.
