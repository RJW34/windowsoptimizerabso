# Work Ledger

Machine source of truth: `manifests/known_defects.json` (143 known minimum defects) plus
`docs/remediation/DEFECT_DISPOSITIONS.md` for anything discovered during remediation.

Rules (from `CLAUDE.md`):

- An item is only `fixed` when a passing test or an explicit proof artifact exists. Changing code is not enough.
- Newly discovered defects are appended to the *Discovered defects* table with a `NEW-` identifier.
- `deferred` means the fix is understood and sequenced but blocked on a prerequisite phase or on
  hardware/OS access this environment does not have (for example a disposable Windows VM).

Status vocabulary: `open`, `in progress`, `fixed`, `removed`, `quarantined`, `deferred`, `rejected`.

## Known defects

| ID | Severity | Phase | Status | Disposition | Tests | Proof | Commit | Summary |
|---|---|---:|---|---|---|---|---|---|
| BASE-001 | critical | 1 | rejected | does not reproduce | tests/test_packaging.py | DECISION_LOG D-001 | — | Source does not parse due to unterminated Windows drive strings. |
| BASE-002 | critical | 1 | fixed | fix | tests/test_cli.py | phase 1 commit | — | `info` uses an empty `SystemInfo` and nonexistent method/schema. |
| BASE-003 | critical | 0 | open | redesign | — | — | — | General optimization calls a nonexistent backup method. |
| BASE-004 | critical | 0 | fixed | redesign (fails closed) | tests/test_containment.py | phase 0 commit | — | Rollback is a no-op that prints success. |
| BASE-005 | high | 1 | fixed | fix | tests/test_containment.py | phase 0 commit | — | Session path suffix logic is incorrect. |
| BASE-006 | critical | 3 | fixed | redesign | tests/test_executor.py | phase 3 commit | — | Loaded results are disconnected from rollback state. |
| BASE-007 | critical | 0 | fixed | fail closed | tests/test_containment.py | phase 0 commit | — | Gaming, privacy, and cleanup shortcuts bypass backup and persistence. |
| BASE-008 | critical | 0 | fixed | fail closed | tests/test_containment.py | phase 0 commit | — | Visual presets bypass engine, confirmation, backup, and session. |
| BASE-009 | high | 1 | fixed | fix | tests/test_planner.py | phase 2 commit | — | Invalid optimization levels silently fall back to SAFE. |
| BASE-010 | critical | 0 | fixed | fix | tests/test_containment.py | phase 0 commit | — | No Windows platform gate prevents mutation elsewhere. |
| BASE-011 | critical | 3 | fixed | redesign | tests/test_planner.py | phase 3 commit | — | `requires_admin` metadata is not enforced. |
| BASE-012 | high | 2 | fixed | redesign | tests/test_planner.py | phase 2 commit | — | `analyze` lists task metadata instead of actual state/applicability. |
| BASE-013 | high | 1 | fixed | fix | tests/test_cli.py | phase 1 commit | — | Failed results do not produce deterministic nonzero CLI exits. |
| BASE-014 | medium | 2 | open | redesign | — | — | — | Services, registry, and power are advertised but not integrated. |
| BASE-015 | medium | 3 | fixed | fix | tests/test_executor.py | phase 3 commit | — | Repeated engine execution accumulates old results. |
| BASE-016 | high | 3 | fixed | redesign | tests/test_executor.py | phase 3 commit | — | Reboot requirement is dynamically attached and not serialized. |
| CORE-001 | critical | 3 | fixed | redesign | tests/test_executor.py | phase 3 commit | — | No centralized exact pre-state capture exists. |
| CORE-002 | critical | 3 | fixed | implement | tests/test_executor.py | phase 3 commit | — | No durable atomic transaction journal exists. |
| CORE-003 | critical | 3 | fixed | implement | tests/test_executor.py | phase 3 commit | — | Operations trust return values without postcondition verification. |
| CORE-004 | critical | 3 | fixed | redesign | tests/test_executor.py | phase 3 commit | — | Execution continues after failure with no coordinated rollback. |
| CORE-005 | high | 2 | fixed | implement | tests/test_planner.py | phase 2 commit | — | No OS-build, hardware, feature, or prerequisite model exists. |
| CORE-006 | high | 2 | fixed | implement | tests/test_planner.py | phase 2 commit | — | No dependency or conflict ordering exists. |
| CORE-007 | critical | 3 | fixed | fix | tests/test_domain.py | phase 2 commit | — | Raw binary registry values cannot be JSON serialized. |
| CORE-008 | high | 3 | fixed | implement | tests/test_executor.py | phase 3 commit | — | Legacy sessions lack schema/version validation. |
| CORE-009 | high | 3 | fixed | implement | tests/test_executor.py | phase 3 commit | — | Session and recovery data have no integrity validation. |
| CORE-010 | critical | 3 | fixed | redesign | tests/test_executor.py | phase 3 commit | — | Rollback is identified only by operation name and boolean result. |
| CORE-011 | critical | 3 | fixed | implement | tests/test_executor.py | phase 3 commit | — | No cancellation, crash, reboot, or incomplete-transaction recovery exists. |
| CORE-012 | high | 2 | fixed | implement | tests/test_planner.py | phase 2 commit | — | No immutable plan digest or state-drift check exists. |
| CORE-013 | high | 3 | fixed | implement | tests/test_executor.py | phase 3 commit | — | Concurrent processes can race. |
| CORE-014 | high | 2 | fixed | implement | tests/test_planner.py | phase 2/3 commits | — | User-scoped operations do not identify intended interactive user. |
| CORE-015 | medium | 3 | fixed | fix | tests/test_executor.py | phase 3 commit | — | Callback failures are swallowed and callbacks are untyped. |
| CORE-016 | high | 3 | fixed | implement | tests/test_domain.py | phase 2 commit | — | Boolean success cannot represent partial/skipped/unsupported/reboot states. |
| CORE-017 | medium | 2 | fixed | redesign | tests/test_domain.py | phase 2 commit | — | Risk ordering relies on enum declaration and ambiguous CUSTOM semantics. |
| BAK-001 | critical | 3 | open | redesign | — | — | — | Backup and engine session formats are disconnected. |
| BAK-002 | high | 4 | open | fix | — | — | — | Service backup records success without checking command results. |
| BAK-003 | critical | 4 | deferred | implement | — | needs a disposable Windows VM (gate G6) | — | Service configuration restore is absent. |
| BAK-004 | critical | 4 | deferred | implement | — | needs a disposable Windows VM (gate G6) | — | Scheduled-task restore is absent. |
| BAK-005 | high | 3 | fixed | fix | tests/test_domain.py | phase 2 commit | — | Checksums are never verified and use MD5. |
| BAK-006 | critical | 3 | fixed | fix | tests/test_executor.py | phase 3 commit | — | Index writes are non-atomic and corruption becomes empty history. |
| BAK-007 | high | 4 | fixed | fix | tests/test_legacy_guards.py | phase 0 commit | — | Missing original path metadata is handled incorrectly. |
| BAK-008 | high | 4 | open | redesign | — | — | — | File rollback creates unmanaged `.rollback` files and can overwrite later edits. |
| BAK-009 | high | 4 | open | redesign | — | — | — | Registry export/import is not exact rollback. |
| BAK-010 | high | 3 | open | implement | — | — | — | Backup/journal storage lacks reparse, ownership, ACL, and disk checks. |
| BAK-011 | high | 3 | fixed | fix | tests/test_containment.py | phase 0 commit | — | Restore-point description is interpolated into PowerShell. |
| BAK-012 | medium | 7 | open | redesign | — | — | — | Age-only cleanup can delete the only recovery path. |
| BAK-013 | high | 3 | open | implement | — | — | — | Recovery artifacts are not verified before mutation. |
| REG-001 | critical | 4 | fixed | fix | tests/test_domain.py | phase 2 commit | — | Rollback captures target type instead of original type. |
| REG-002 | high | 4 | fixed | implement | tests/test_domain.py | phase 2 commit | — | Registry view is implicit. |
| REG-003 | high | 4 | fixed | implement | tests/test_backends_fake.py | phase 2/3 commits | — | Writes/deletes are not read-back verified. |
| REG-004 | critical | 4 | fixed | redesign | tests/test_planner.py | phase 2 commit | — | Generic broad registry mutation can be exposed. |
| REG-005 | high | 4 | fixed | fix | tests/test_backends_fake.py | phase 2 commit | — | Unknown registry types default to string. |
| REG-006 | critical | 4 | open | fix | — | — | — | Visual code mutates `UserPreferencesMask` outside returned rollback. |
| CLN-001 | critical | 4 | open | fix | — | — | — | Cleanup reports success despite deletion/permission errors. |
| CLN-002 | critical | 4 | open | redesign | — | — | — | Irreversible cleanup is labeled SAFE and bundled broadly. |
| CLN-003 | high | 4 | open | fix | — | — | — | Disk Cleanup and Recycle Bin return codes are ignored or errors suppressed. |
| CLN-004 | high | 4 | open | redesign | — | — | — | Browser caches assume only Default profiles and ignore running browsers. |
| CLN-005 | high | 4 | open | fix | — | — | — | Firefox cache matching yields a directory that is skipped. |
| CLN-006 | high | 4 | open | fix | — | — | — | Cleanup `recursive` is unused and containment/reparse defense is absent. |
| CLN-007 | high | 4 | open | remove | — | — | — | Prefetch deletion is presented as optimization. |
| CLN-008 | high | 4 | open | redesign | — | — | — | Diagnostic/log deletion removes evidence and overlaps targets. |
| CLN-009 | medium | 4 | open | fix | — | — | — | Analysis can double-count overlaps and cannot represent locks/not-applicable. |
| PRV-001 | critical | 4 | open | fix | — | — | — | Registry rollback ignores restoration failures and returns true. |
| PRV-002 | critical | 4 | open | redesign | — | — | — | Telemetry tasks are disabled without pre-state/rollback. |
| PRV-003 | critical | 4 | open | redesign | — | — | — | Hosts rollback replaces whole file and can erase later edits. |
| PRV-004 | high | 4 | open | fix | — | — | — | Host list contains invalid/stale entries including a port suffix. |
| PRV-005 | high | 4 | open | redesign | — | — | — | Policy behavior varies by Windows edition/build but applicability is absent. |
| PRV-006 | high | 4 | open | fix | — | — | — | Absent/protected tasks are counted as failures and output parsing is locale-dependent. |
| PRV-007 | critical | 4 | open | fix | — | — | — | HKCU privacy changes may target elevated account. |
| PRV-008 | high | 4 | open | remove | — | — | — | Legacy Cortana/web-search settings are conflated and may be obsolete. |
| PRV-009 | medium | 4 | open | fix | — | — | — | DNS flush after hosts modification is unchecked. |
| STA-001 | critical | 4 | open | fix | — | — | — | Startup entry can be deleted after failed destination write. |
| STA-002 | high | 4 | open | fix | — | — | — | Naive `Run` replacement corrupts `RunOnce` paths. |
| STA-003 | high | 4 | open | fix | — | — | — | Falsy startup values are treated as absent. |
| STA-004 | high | 4 | open | fix | — | — | — | Task claims no admin while mutating HKLM startup. |
| STA-005 | critical | 4 | open | remove | — | — | — | Broad substring list automatically disables user-selected apps. |
| STA-006 | high | 4 | open | fix | — | — | — | Scheduled-task CSV is hand-parsed and locale/quote fragile. |
| STA-007 | high | 4 | open | fix | — | — | — | Rollback ignores per-item failures and returns true. |
| STA-008 | high | 4 | open | redesign | — | — | — | Boot optimization comments/settings are inaccurate or obsolete. |
| STA-009 | medium | 4 | open | fix | — | — | — | `get_boot_time` returns uptime, not boot duration. |
| STA-010 | medium | 1 | removed | remove (claim deleted) | tests/test_cli.py | phase 1 commit | — | Shell-extension cleanup is advertised but absent. |
| SVC-001 | critical | 4 | fixed | fix | tests/test_backends_fake.py | phase 2 commit | — | Critical-service protection is case-sensitive while Windows names are case-insensitive. |
| SVC-002 | critical | 4 | open | fix | — | — | — | Dependencies/dependents are queried but not enforced. |
| SVC-003 | critical | 4 | open | fix | — | — | — | Stop failure does not prevent disable. |
| SVC-004 | critical | 4 | open | fix | — | — | — | Gaming profile disables Xbox services. |
| SVC-005 | critical | 4 | open | fix | — | — | — | Default profile guesses Manual rather than restoring prior state. |
| SVC-006 | high | 4 | open | redesign | — | — | — | Hardcoded safe list ignores build, hardware, and user features. |
| SVC-007 | high | 4 | open | fix | — | — | — | Localized `sc` output is manually parsed and description is never read. |
| SVC-008 | high | 4 | deferred | implement | — | needs a disposable Windows VM (gate G6) | — | Exact service config and transition waiting are absent. |
| SVC-009 | medium | 2 | open | fix | — | — | — | Service manager is not integrated despite README claims. |
| NET-001 | critical | 4 | open | remove | — | — | — | Comments and registry settings frequently do not match. |
| NET-002 | critical | 4 | open | remove | — | — | — | Global `TcpAckFrequency`/`TCPNoDelay` writes are wrong-scoped. |
| NET-003 | high | 4 | open | remove | — | — | — | Legacy/unsupported `netsh` settings are forced. |
| NET-004 | critical | 4 | open | redesign | — | — | — | Netsh changes have no pre-state/rollback and leave partial changes. |
| NET-005 | high | 4 | open | fix | — | — | — | Active adapter detection through registry truthiness is fragile. |
| NET-006 | high | 4 | open | remove | — | — | — | DNS TTL/negative-cache changes are presented as optimization without evidence. |
| NET-007 | critical | 4 | open | remove | — | — | — | Network stack reset is destructive, unjournaled, and not reversible. |
| NET-008 | high | 4 | open | implement | — | — | — | No VPN/domain/virtual adapter/Wi-Fi/NIC topology applicability exists. |
| NET-009 | high | 4 | open | fix | — | — | — | Network analysis misinterprets registry values. |
| NET-010 | high | 6 | open | implement | — | — | — | No latency/jitter/throughput or game-netcode benchmark supports claims. |
| GAM-001 | critical | 4 | open | redesign | — | — | — | HAGS operation mixes Game Mode, DVR, scheduling, and HDCP changes. |
| GAM-002 | critical | 4 | open | remove | — | — | — | NVIDIA optimization changes TDR timeouts and calls them shader-cache settings. |
| GAM-003 | critical | 4 | open | remove | — | — | — | NVIDIA display container is disabled without validation/rollback. |
| GAM-004 | critical | 4 | open | remove | — | — | — | Memory operation hardcodes L2 cache and applies unsupported folklore. |
| GAM-005 | high | 4 | open | redesign | — | — | — | Power optimization duplicates Ultimate Performance and does not capture original. |
| GAM-006 | high | 4 | open | remove | — | — | — | Mouse/keyboard/hover preferences are treated as latency optimization. |
| GAM-007 | high | 4 | open | redesign | — | — | — | System-wide fullscreen/DWM recipes are legacy/undocumented. |
| GAM-008 | high | 6 | open | implement | — | — | — | No GPU vendor/driver/display capability detection exists. |
| GAM-009 | critical | 6 | open | implement | — | — | — | No per-game executable/profile/session lifecycle exists. |
| GAM-010 | high | 6 | open | implement | — | — | — | No benchmark supports gaming claims. |
| GAM-011 | high | 6 | open | fix | — | — | — | Gaming changes can disable capture despite OBS/devstream needs. |
| VIS-001 | critical | 4 | open | fix | — | — | — | Performance preset discards child rollback data. |
| VIS-002 | critical | 4 | open | remove | — | — | — | Hardcoded UserPreferencesMask and guessed defaults are version/user specific. |
| VIS-003 | high | 4 | open | remove | — | — | — | Legacy/incorrect DWM and taskbar settings are mislabeled. |
| VIS-004 | high | 4 | open | implement | — | — | — | Visual changes ignore accessibility and preference impact. |
| VIS-005 | high | 4 | open | fix | — | — | — | HKCU visual operations have no explicit target user. |
| VIS-006 | medium | 4 | fixed | implement | tests/test_executor.py | phase 3 commit | — | Visual operations do not model Explorer/logoff activation requirements. |
| SYS-001 | high | 1 | fixed | fix | tests/test_cli.py | phase 1 commit | — | WMI is imported but unused and hardware data does not drive applicability. |
| SYS-002 | high | 2 | open | implement | — | — | — | GPU, driver, display, battery, virtualization, domain/VPN, restore-point, and interactive-user data are missing. |
| SYS-003 | medium | 2 | fixed | fix | tests/test_cli.py | phase 1 commit | — | Reports can expose machine identifiers without redaction contract. |
| SYS-004 | medium | 1 | fixed | fix | tests/test_cli.py | phase 1 commit | — | Timestamps are naive and ambiguous across recovery. |
| PKG-001 | critical | 1 | open | implement | — | — | — | No tests are committed. |
| PKG-002 | critical | 7 | open | implement | — | — | — | No GitHub Actions or commit checks exist. |
| PKG-003 | high | 1 | fixed | fix | tests/test_packaging.py | phase 1 commit | — | pyproject and requirements disagree; runtime/dev/unused packages mix. |
| PKG-004 | high | 1 | fixed | fix | tests/test_packaging.py | phase 1 commit | — | Package is named `src` and metadata has placeholders. |
| PKG-005 | high | 7 | fixed | fix | tests/test_packaging.py | phase 1 commit | — | Version 1.0.0 overstates maturity. |
| PKG-006 | high | 1 | fixed | fix | tests/test_cli.py | phase 1 commit | — | README advertises absent GUI/backup/restore/profiles/dirs/commands. |
| PKG-007 | high | 7 | open | fix | — | — | — | MIT is declared but LICENSE absent; CONTRIBUTING referenced but absent. |
| PKG-008 | high | 7 | open | implement | — | — | — | No tags/releases/branch protection/dependency alerts/code scanning. |
| SEC-001 | critical | 3 | fixed | fix | tests/test_containment.py | phase 0 commit | — | Elevated commands rely on PATH. |
| SEC-002 | critical | 3 | fixed | fix | tests/test_containment.py | phase 0 commit | — | PowerShell source interpolation permits injection. |
| SEC-003 | critical | 3 | fixed | implement | tests/test_planner.py | phase 2 commit | — | Generic mutation primitives could be exposed to an agent. |
| SEC-004 | critical | 4 | open | implement | — | — | — | No canonical-path/reparse defense protects cleanup/backup. |
| SEC-005 | high | 3 | fixed | implement | tests/test_planner.py | phase 2 commit | — | State can change between plan and apply. |
| SEC-006 | high | 7 | open | implement | — | — | — | No dependency scanning, SBOM, or artifact verification. |
| TST-001 | critical | 3 | fixed | implement | tests/test_backends_fake.py | phase 2 commit | — | No fake backend or fault-injection framework exists. |
| TST-002 | critical | 5 | deferred | implement | — | needs a disposable Windows VM (gate G6) | — | No disposable Windows VM apply/reboot/rollback proof exists. |
| TST-003 | high | 3 | fixed | implement | tests/test_executor.py | phase 3 commit (fakes; VM deferred) | — | No concurrency/crash/corruption/disk-full/locale/Unicode/reparse tests exist. |
| TST-004 | critical | 5 | fixed | implement | tests/test_executor.py | phase 3 commit (fakes; VM deferred) | — | No exact state-equality assertion exists after rollback. |
| PRD-001 | high | 6 | open | redesign | — | — | — | Repository is global tweak collection rather than game-profile tool. |
| PRD-002 | high | 6 | open | implement | — | — | — | Profiles lack schema/version/provenance/conflict/evidence. |
| PRD-003 | high | 6 | open | implement | — | — | — | No automatic restore after game exit/crash. |
| PRD-004 | high | 6 | open | implement | — | — | — | No user-readable state diff/tradeoff/evidence display. |
| PRD-005 | medium | 7 | removed | remove | tests/test_packaging.py | phase 1 commit | — | GUI dependencies/commands are advertised without implementation. |

## Discovered defects

| ID | Severity | Status | Disposition | Location | Summary |
|---|---|---|---|---|---|
| NEW-001 | high | fixed | rejected (does not reproduce) | `src/modules/cleanup.py` | Pack defect BASE-001 claims the tree does not parse. At the pinned baseline all 15 modules parse and byte-compile; the drive literals are correctly escaped. Recorded in `DECISION_LOG.md` D-001. |
