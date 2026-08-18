# 08 — CI, Release, and Governance

## Pull-request CI

Run at minimum:

- source compilation
- Ruff
- static typing
- unit tests
- fake-backend contracts
- fault-injection tests
- CLI tests
- documentation command tests
- wheel/sdist build
- clean install and console smoke
- JSON/schema validation
- dependency review
- CodeQL or equivalent

Use Windows jobs for Windows imports and a non-Windows job to prove fail-closed behavior.

## Scheduled/nightly

- broader Python matrix
- dependency updates
- Windows VM integration
- reboot/recovery suite
- package variants
- security scans
- benchmark smoke/regression

Hosted runners do not replace snapshotted VMs for destructive and reboot tests.

## Governance

Document and enable:

- protected default branch
- required reviews/checks
- no force push
- no protected-branch deletion
- verified release process
- code owners for privileged mutation code
- issue/PR templates
- security policy
- dependency update policy

## Versioning

The current `1.0.0` claim is not credible. Move to an honest pre-release such as `0.1.0a1`, with project-approved versioning and changelog.

## Required docs

- accurate `README.md`
- `LICENSE`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `CHANGELOG.md`
- architecture
- threat model
- support matrix
- operation risk/evidence catalog
- CLI reference
- profile authoring
- troubleshooting/recovery
- Windows VM validation
- release checklist

No docs advertise a GUI or absent feature.

## Release artifacts

Before external release:

- reproducible wheel/sdist
- optional Windows executable only after tested UAC behavior
- checksums
- SBOM
- dependency/license inventory
- signatures when available
- proof-bundle reference
- limitations/residual risks

## Security automation

Enable dependency automation, code scanning, secret scanning where permissions permit, dependency review, artifact verification, and branch protection. If settings cannot be changed, provide exact operator steps without claiming they were applied.
