# Decision Log

Records deviations from the remediation pack, and design decisions where the pack's prescribed
implementation was unsound, ambiguous, or not reproducible. Per `CLAUDE.md`, an invariant may be
satisfied by a different design, but it may not be silently weakened.

---

## D-001 — BASE-001 does not reproduce at the pinned baseline

**Date:** 2026-08-18
**Pack claim:** `BASELINE.json` / `00_CURRENT_STATE_AND_MISSION.md` / `known_defects.json` BASE-001 assert
that the source *does not parse*, because `src/modules/cleanup.py` contains unterminated `C:\` literals in
the `cleanmgr` command and the `run_disk_cleanup` default argument, and that importing `src.main` therefore
fails.

**Observed at `fed422ddc1b5808ad6c98908a96231a98b6ed625`:**

```
$ python3 tools/static_baseline_audit.py --root . --output artifacts/remediation-proof/baseline_static_audit.json
{"python_files": 15, "parse_failures": 0, "compile_failures": 0, ...}
```

The literals in question are `"C:"` (line 391), `drive: str = "C:"` (line 499) and `"C:\\Windows"` — all
valid Python. All 15 modules parse and byte-compile.

**Disposition:** BASE-001 is **rejected — does not reproduce**. `src.main` does fail to import in a bare
environment, but with `ModuleNotFoundError: No module named 'typer'`, i.e. a missing dependency, not a
syntax error. That is a real and separate problem (PKG-003/PKG-004) and is fixed by the packaging work.

**Consequence for the pack's sequencing:** `02_IMPLEMENTATION_SEQUENCE.md` argues containment must precede
the syntax fix because "repairing syntax alone would expose unsafe shortcut commands". Since the tree already
parses, those shortcut commands are exposed *today* — anyone with the dependencies installed can run
`winopt gaming -y` and mutate the host. Containment is therefore more urgent than the pack assumed, and is
the first code change made (Phase 0), before any restructuring.

**Residual risk:** the audit was reproduced on CPython 3.11 on Linux. A Windows-only parse failure is not
plausible for this class of defect, so no further verification was done.

---

## D-002 — Containment implemented as a default-deny guard rather than by deleting commands

**Date:** 2026-08-18
**Requirement:** Gate G0 — "no accessible command can mutate a machine" during the unsafe phases.

**Options considered:**

1. Delete the mutating CLI commands and module methods outright.
2. Keep them and route every mutation through a single default-deny guard.

**Decision:** option 2, `windowsoptimizerabso.safety`. Deleting the code first would destroy the domain
knowledge (registry paths, service lists, cleanup targets) that Phase 4 has to triage operation by
operation, and it would make the legacy behaviour unavailable for differential testing against the new
typed operations.

The guard is default-deny and fails closed on four axes, all of which must pass before any mutation runs:

1. `WINOPT_ALLOW_MUTATION=1` must be set explicitly (no CLI flag, no config file — an environment variable
   an operator has to set deliberately).
2. The platform must be Windows.
3. `WINOPT_UNSAFE_LEGACY=1` must additionally be set to reach *legacy* (unported, unjournaled) mutation.
4. Subprocess invocations must match the read-only allowlist, or be explicitly declared mutating by a
   caller that has already passed 1–3.

**Why an environment variable rather than a flag:** a flag can be added to a copy-pasted command line by a
user who does not understand it, and would be trivially reachable by an agent driving the CLI. The variable
has to be set in the process environment of whoever launches the tool, which keeps it out of the
"paste this command" attack surface.

**Residual risk:** a caller inside the package can still call `winreg` directly and bypass the guard. This
is mitigated by a test that asserts no module outside `backends/windows/` and `legacy/` imports `winreg` or
`subprocess` directly, but it is a lint-grade control, not a sandbox.

---

## D-003 — Legacy code quarantined under `legacy/` instead of being rewritten in place

**Date:** 2026-08-18
**Requirement:** `01_TARGET_ARCHITECTURE.md` mandates migrating away from a package literally named `src`
and separating inspection / planning / execution / journaling / rollback.

**Decision:** the package moved to `src/windowsoptimizerabso/`, and the entire legacy tree moved verbatim to
`src/windowsoptimizerabso/legacy/{core,modules}` — preserving its internal relative imports — while the new
architecture is built alongside it in `domain/`, `backends/`, `journal/`, `executor/`, and `cli/`.

`legacy/` is import-clean and read-only-by-default, but nothing in it is on the supported path: it is
reference material for Phase 4 porting and for differential tests. `legacy/__init__.py` documents this and
the module import emits no side effects.

**Residual risk:** two coexisting models of "an operation" for the duration of Phase 4. Mitigated by the
legacy tree being unreachable from the CLI.

---

## D-004 — Journal is SQLite in WAL mode, and pre-state durability is fsync-verified

**Date:** 2026-08-18
**Requirement:** Gate G3 — pre-state durable before mutation; transitions journaled; corruption handled.

**Decision:** followed the pack's SQLite/WAL recommendation. Two additions the pack did not specify:

- The `PRESTATE_DURABLE` transition performs an explicit `PRAGMA wal_checkpoint(FULL)` and an `os.fsync` of
  the database file *before* the executor is allowed to leave the pre-state phase. A committed SQLite
  transaction in WAL mode is durable against process crash by default, but not against machine power loss
  until the WAL is checkpointed — and power loss mid-apply is exactly the scenario rollback exists for.
- Every captured state blob is stored with a SHA-256 digest computed over its canonical encoding, verified
  on read. A journal that silently returns corrupted pre-state is worse than one that refuses to roll back,
  because it would write wrong values over a live system.

**Residual risk:** `fsync` on Windows via `os.fsync` maps to `FlushFileBuffers`, which some virtual disks
and cheap SSDs acknowledge without actually flushing. This cannot be fixed in user mode and is documented
as a known limitation in the risk register.

---

## D-005 — Windows-only work is deferred, not claimed

**Date:** 2026-08-18
**Requirement:** Gates G4/G6 require apply → reboot → verify → rollback → reboot equality proven in a
disposable Windows VM.

**Decision:** this environment is Linux with no Windows VM, no `winreg`, and no `sc.exe`. Those gates are
recorded as **deferred** in the work ledger with the exact reproduction commands, and every locally possible
substitute is implemented and tested: the full lifecycle including reverse-order rollback, exact-state
equality, fault injection at every boundary, and crash recovery is proven against the deterministic fake
backends.

Per `CLAUDE.md`, the project is **not** labelled release-ready while those gates remain open, and the
version is `0.0.1a1`.
