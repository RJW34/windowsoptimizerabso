# Security

## Reporting a vulnerability

Report privately through GitHub's **Security → Report a vulnerability** on
<https://github.com/RJW34/windowsoptimizerabso>. Please do not open a public issue for anything
that would let someone take over a machine running this tool.

Include what you did, what happened, and — if the finding depends on Windows behaviour — the build
number you saw it on. A proof of concept that runs inside a disposable VM is ideal.

## What this project treats as a vulnerability

This tool is designed to run elevated and change a Windows machine, so its threat model is unusual.
The things it must never do:

- **Execute anything it was not told to.** Operations resolve system binaries by absolute path under
  `%SystemRoot%`, never through `PATH`, and never through a shell. A finding that gets an arbitrary
  binary or script executed is critical, including through a crafted plan file, a profile, a
  registry value, or a command's own output.
- **Widen an operation's blast radius.** A plan carries operation ids that resolve only through a
  code-side registry, and parameters validated against a declared schema. A finding that lets a
  plan, profile, or environment variable make an operation touch a target it does not declare is
  critical.
- **Report a change as reverted when it was not.** A rollback that claims success without restoring
  and verifying the captured state is a security bug here, not just a correctness bug: it tells an
  operator a machine is clean when it is not.
- **Leak machine identity by default.** `winopt inspect` redacts the hostname and registered owner
  unless `--include-identifiers` is passed. A path that leaks them into normal output is a finding.
- **Escape containment.** While the project is pre-alpha, mutation requires `WINOPT_ALLOW_MUTATION`
  (plus `WINOPT_UNSAFE_LEGACY` for the quarantined prototype) and a Windows host. Any way to mutate
  without both is a finding.

## Known limitations, deliberately

These are documented rather than fixed, and are not treated as vulnerabilities:

- **`os.fsync` is trusted.** Durability of captured pre-state depends on the platform honouring
  `FlushFileBuffers`. Some virtual disks and consumer SSDs acknowledge without flushing. This cannot
  be fixed in user mode.
- **A recycled PID reads as a live lock holder.** The execution lock probes the owning PID; a
  recycled PID keeps the lock held. This fails in the safe direction — a second executor refuses
  rather than two running at once.
- **The machine fingerprint is a redaction, not an anonymisation.** It is an unsalted hash of the
  hostname, chosen so that reports from one machine correlate. A hostname you can guess is a
  fingerprint you can confirm.
- **The legacy tree is guarded, not audited.** Everything under `windowsoptimizerabso/legacy/` is the
  unfixed prototype. It is unreachable from the CLI and behind two opt-ins. Findings in it are
  tracked as remediation defects, not as vulnerabilities, until an operation is ported.

## Supported versions

None. This is pre-alpha software with open acceptance gates
(`manifests/acceptance_gate_matrix.csv`). There is no supported release to backport a fix to; fixes
land on the default branch.
