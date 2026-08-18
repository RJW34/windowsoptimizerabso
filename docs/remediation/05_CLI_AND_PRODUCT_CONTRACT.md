# 05 — CLI and Product Contract

## Default behavior

Running the application without explicit apply must not mutate.

Recommended commands:

```text
winopt inspect
winopt inspect --json
winopt profiles list
winopt profiles show <profile-id>
winopt plan --profile <profile-id> --output <plan.json>
winopt plan --operations <allowlisted-ids> --output <plan.json>
winopt apply --plan <plan.json> --confirm <digest>
winopt verify --transaction <id>
winopt rollback --transaction <id>
winopt history
winopt recover
winopt doctor
```

Legacy commands such as `gaming`, `privacy`, `cleanup`, or `visual --preset` may exist only as aliases that generate a plan. They may not invoke mutators directly.

## Plan display

Before approval display:

- target machine and user
- profile/version
- each operation ID
- current and desired state
- whether a change is needed
- risk and user-visible tradeoffs
- evidence status
- admin requirement
- reboot/logoff/restart requirement
- backup/journal strategy
- verification and rollback method
- conflicts
- plan digest

Do not use phrases such as “maximum performance” without quantified evidence.

## Confirmation

Interactive confirmation shows the digest and requires clear affirmative action. Automation supplies the digest explicitly. `--yes` alone is not adequate for a privileged immutable plan.

## Exit codes

Define and test stable semantics, for example:

```text
0 success or verified no-op
2 usage/input/schema error
3 unsupported platform/capability
4 privilege or target-user error
5 stale plan/drift detected
6 apply failed before mutation
7 partial apply or verification failure
8 rollback required
9 rollback partial/failed
10 recovery required
11 reboot/logoff required before final verification
12 internal invariant failure
```

Exact numbers may differ, but semantics remain documented and tested.

## Output

- Human-readable Rich output.
- Stable JSON for automation.
- No raw object representations.
- No unnecessary PII.
- Include transaction/proof paths.
- Never print “complete” unless verification completed.

## Cleanup

Cleanup is destructive. The plan lists exact paths or summarized inventories, exclusions, estimated bytes, lock state, and reversibility. Recycle Bin emptying, log deletion, prefetch deletion, and browser cache deletion are never silently included in a “safe” bundle.

## Rollback

Output includes transaction state, attempted/restored operations, verification, conflicts, residual drift, reboot requirement, and nonzero status on partial/failed rollback. There is no success message after a placeholder.

## Documentation

Every README/docs command example executes in CI. Remove GUI claims until a tested GUI exists. Remove feature claims until implemented and proven.
