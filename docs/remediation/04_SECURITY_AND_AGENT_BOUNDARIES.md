# 04 — Security and Agent Boundaries

## Threat model

The application may run elevated and affect registry, services, scheduled tasks, files, networking, power state, and user settings. Threats include accidental destructive behavior, stale or malicious profiles, command/path injection, PATH hijacking under elevation, reparse-point escape, active-user confusion under UAC, time-of-check/time-of-use drift, backup tampering, concurrent execution, crash during mutation, remote-agent overreach, sensitive logs, and supply-chain compromise.

## Privilege model

### Unprivileged process

May inspect, load trusted profiles, create immutable plans, show diffs/risks, view history, and request recovery. It may not mutate.

### Privileged executor

May accept only a supported plan schema, validated digest, machine identity, target user SID, allowlisted operation registry, and constrained parameters. It rejects arbitrary commands, scripts, registry paths, service/task names, and filesystem paths.

## Subprocess rules

- Resolve trusted Windows executables from a trusted system directory.
- Do not rely on `PATH` when elevated.
- Do not use `shell=True`.
- Do not interpolate user-controlled text into PowerShell source.
- Prefer native APIs or structured invocation.
- Use controlled environment and working directory.
- Set explicit timeouts and terminate process trees safely.
- Capture and sanitize stdout/stderr.
- Distinguish unsupported syntax, permission failure, and operational failure.
- Avoid locale-dependent parsing.

## Registry rules

- Canonicalize hive and view.
- Identify target user SID explicitly.
- Preserve exact type, data, and existence.
- Read back after mutation.
- Do not fall back unknown types to string.
- Do not accept arbitrary paths from profiles.
- Record security context.

## Filesystem rules

- Canonicalize paths and verify the final target remains inside the approved root.
- Reject reparse traversal unless explicitly supported and tested.
- Use atomic writes.
- Preserve encoding, newlines, metadata, and security descriptors when relevant.
- Do not replace a whole shared file during rollback when only a managed block changed.
- Detect later unrelated edits and report conflict.
- Secure backup/journal directories against other users and reparse attacks.

## Journal security

- Single-writer lock.
- Atomic durable commits.
- SHA-256 or stronger artifact hashes.
- Verify before restore.
- Schema versions and migrations.
- Refuse corrupted recovery state instead of silently resetting history.
- Redact secrets and personal identifiers from reports.
- Keep exact recovery data local and access-controlled.

## Agent boundary

DEKU, Claude, or another remote agent may by default inspect, plan, compare profiles, request benchmarks, explain risk, and read sanitized proof.

An agent may not by default execute arbitrary shell/PowerShell, write arbitrary registry values, disable arbitrary services/tasks, delete arbitrary files, change hosts/networking, apply unsigned profiles, bypass confirmation, suppress rollback, choose another target user, or run on an unsupported machine.

A future agent integration calls a narrow typed local API. Human approval binds to the immutable plan digest. The elevated executor never trusts remote prose.

## Supply chain

- Minimize and lock dependencies.
- Run dependency review and vulnerability scanning.
- Generate SBOM and checksums.
- Sign release artifacts when infrastructure exists.
- Add code scanning.
- Protect release branches and require checks.
- Never download or execute unverified optimization payloads.

## Cancellation and recovery

`Ctrl+C`, termination, power loss, and reboot are expected failure modes. The journal must reveal whether an operation crossed the mutation boundary. Recovery re-inspects state rather than assuming the last call succeeded or failed.
