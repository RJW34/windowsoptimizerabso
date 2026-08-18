# 09 — Definition of Done

The project is incomplete until every blocking gate passes.

## A — Containment

- Legacy source cannot mutate the host during remediation.
- No false rollback success remains.
- No direct shortcut bypass exists.
- Baseline/pre-alpha warning is clear.

## B — Build/package

- All Python compiles/imports.
- Wheel/sdist build and clean install.
- Console entry works.
- Dependency files agree and are reproducible.

## C — Truthful inspection

- System state is gathered correctly.
- Unsupported platforms fail clearly.
- Inspection never mutates.
- Unsupported, absent, and failed are distinct.
- Normal reports redact PII.

## D — Plan/approval

- Plans are immutable, versioned, digest-bound.
- Operations are typed and allowlisted.
- Machine/user identity is explicit.
- Applicability, conflict, risk, evidence, verification, and rollback are present.
- Drift invalidates plans.

## E — Transaction core

- Pre-state is durable before mutation.
- Lifecycle transitions are journaled.
- Concurrent apply is prevented.
- Interruption/reboot recovery works.
- Binary/typed state serializes safely.
- Partial outcomes cannot return success.

## F — Exact rollback

- Every retained mutation has rollback.
- Restore is reverse-order and verified.
- Conflicts preserve unrelated later changes or require explicit resolution.
- Partial/failed rollback is nonzero and explicit.
- Apply/reboot/rollback/reboot equality is proven in disposable VMs.

## G — Module correctness

- Every legacy operation has a disposition.
- Folklore is removed/quarantined.
- Services are dependency-aware/case-insensitive.
- Tasks/services restore exactly.
- Cleanup is scoped/inventoried/honest.
- Network/gaming are capability-gated/evidence-backed.
- User preferences and OBS/capture are preserved by default.

## H — Tests

- Static, unit, contract, fault-injection, CLI, packaging, security, and VM tests pass.
- Coverage thresholds pass.
- No blocking test skipped.
- Exact rollback equality passes.
- Non-Windows mutation guard passes.

## I — Product profiles

- Profile schema is constrained/versioned.
- Rivals 2 and Slippi produce readable plans.
- Session restoration works after normal exit/recovery.
- Claimed benefits have benchmark evidence.
- Zero-change profiles are valid.

## J — CI/governance

- CI/security automation exists.
- Branch-protection policy is documented/applied.
- Docs match code.
- Version reflects pre-release.
- License/security/changelog/support docs exist.

## K — Final proof

- Final report exists.
- Proof manifest validates.
- Every known and newly found defect has disposition.
- Residual risks are explicit.
- Reproduction commands are complete.
- Independent audit reports no unresolved blocker.

A plan, partial implementation, large test count without VM proof, or “works on my machine” does not satisfy completion.
