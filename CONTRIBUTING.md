# Contributing

## Before anything else

Read [`CLAUDE.md`](CLAUDE.md) and [`docs/remediation/`](docs/remediation/). This repository is
mid-remediation against a register of 143 known defects, and the rules there are not style
preferences — they are what stops the tool lying to someone about the state of their machine.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pytest && ruff check . && mypy src/windowsoptimizerabso
```

## The rules that are not negotiable

**Never run a mutating command against a machine you care about.** Not the legacy tree, not a
half-ported operation, not "just to see". Use a disposable VM or Windows Sandbox with a snapshot you
can roll back to. `WINOPT_ALLOW_MUTATION` and `WINOPT_UNSAFE_LEGACY` exist for that and nothing else.

**Nothing may report success it did not verify.** If an operation cannot re-read the machine and
confirm its postcondition, its status is `PARTIAL`, not `SUCCEEDED`. If a rollback cannot compare the
restored state against what it captured, it is `ROLLBACK_PARTIAL`. The whole project exists because
the baseline printed "Rollback complete." having done nothing.

**Every mutation goes through `safety.guard_mutation` or `safety.guarded_run`.** Do not import
`subprocess` or call `winreg`'s write functions outside `backends/windows/`. Three tests enforce
this structurally; if you find yourself needing to add a `# noqa` to get around one of them, that is
the discussion to have on the PR, not a thing to slip past.

**A defect is not fixed until a test proves it.** `docs/remediation/WORK_LEDGER.md` only moves an
item to `fixed` with a passing test or an explicit proof artifact named in the row. Changing code is
not enough.

## Adding an operation

Every operation needs, without exception:

1. An `Evidence` record with a primary source — Microsoft or the relevant hardware vendor — and the
   date it was checked. Windows behaviour changes by build; an undated citation cannot be
   re-verified. Blogs, forums, videos and tweak compilations generate hypotheses, they do not settle
   them, and an operation whose only justification is a tweak list gets quarantined or removed.
2. Stated tradeoffs. `HIGH` risk and above will not construct without them.
3. `capture`, `apply`, `restore` and `check_applicability`. `check_applicability` returning
   `already_satisfied` *is* the postcondition the executor verifies against, so it has to be honest
   about what "done" means.
4. Exact reversibility, or `Risk.IRREVERSIBLE` and an honest plan rendering. There is no third
   option where something is "mostly" reversible.
5. Declared parameters. An operation may not accept an arbitrary registry path, service name, shell
   string or deletion root from a profile.
6. Tests: applicability including the not-applicable case, apply, verification failure, exact
   rollback, and at least one injected fault.

If an operation is user-scoped, it must name the target SID. An elevated process's `HKEY_CURRENT_USER`
is the elevating account's hive, not the interactive user's, and the state types will refuse to be
constructed without one.

## Removing an operation

Removing a legacy tweak is a normal and expected contribution. Record the disposition in the work
ledger with a reason. "It was in the baseline" is not a reason to keep something.

## Pull requests

- Small and focused. One operation ported, or one defect fixed, per PR.
- Reference the defect IDs you are addressing.
- CI must be green: tests on Linux and Windows, ruff, mypy, packaging, CodeQL, pip-audit.
- Update `docs/remediation/WORK_LEDGER.md` in the same PR as the fix.
- If you deviate from what the remediation docs prescribe, add an entry to
  `docs/remediation/DECISION_LOG.md` explaining what you did instead and why the invariant still
  holds. Choosing a different design is fine; weakening an invariant quietly is not.

## Commit messages

Say what changed and why it was wrong before. A reader six months from now needs to know which
defect a line of defensive code is defending against — that is why the comments in this codebase
cite defect IDs.
