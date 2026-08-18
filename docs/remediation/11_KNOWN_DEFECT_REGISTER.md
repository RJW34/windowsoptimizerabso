# 11 — Known Defect Register

Baseline: `fed422ddc1b5808ad6c98908a96231a98b6ed625`

Known minimum requirements: **143** (56 critical, 73 high, 14 medium).

The JSON manifest is the machine-readable source of truth. This table is a navigation aid. New defects must be appended to the work ledger.

| ID | Severity | Area | Phase | Default disposition | Summary |
|---|---|---|---:|---|---|
| BASE-001 | critical | build | 1 | fix | Source does not parse due to unterminated Windows drive strings. |
| BASE-002 | critical | cli | 1 | fix | `info` uses an empty `SystemInfo` and nonexistent method/schema. |
| BASE-003 | critical | backup | 0 | redesign | General optimization calls a nonexistent backup method. |
| BASE-004 | critical | rollback | 0 | redesign | Rollback is a no-op that prints success. |
| BASE-005 | high | cli | 1 | fix | Session path suffix logic is incorrect. |
| BASE-006 | critical | rollback | 3 | redesign | Loaded results are disconnected from rollback state. |
| BASE-007 | critical | safety | 0 | redesign | Gaming, privacy, and cleanup shortcuts bypass backup and persistence. |
| BASE-008 | critical | safety | 0 | redesign | Visual presets bypass engine, confirmation, backup, and session. |
| BASE-009 | high | cli | 1 | fix | Invalid optimization levels silently fall back to SAFE. |
| BASE-010 | critical | platform | 0 | fix | No Windows platform gate prevents mutation elsewhere. |
| BASE-011 | critical | privilege | 3 | redesign | `requires_admin` metadata is not enforced. |
| BASE-012 | high | analysis | 2 | redesign | `analyze` lists task metadata instead of actual state/applicability. |
| BASE-013 | high | cli | 1 | fix | Failed results do not produce deterministic nonzero CLI exits. |
| BASE-014 | medium | architecture | 2 | redesign | Services, registry, and power are advertised but not integrated. |
| BASE-015 | medium | state | 3 | fix | Repeated engine execution accumulates old results. |
| BASE-016 | high | state | 3 | redesign | Reboot requirement is dynamically attached and not serialized. |
| CORE-001 | critical | transaction | 3 | redesign | No centralized exact pre-state capture exists. |
| CORE-002 | critical | transaction | 3 | implement | No durable atomic transaction journal exists. |
| CORE-003 | critical | verification | 3 | implement | Operations trust return values without postcondition verification. |
| CORE-004 | critical | failure handling | 3 | redesign | Execution continues after failure with no coordinated rollback. |
| CORE-005 | high | applicability | 2 | implement | No OS-build, hardware, feature, or prerequisite model exists. |
| CORE-006 | high | dependencies | 2 | implement | No dependency or conflict ordering exists. |
| CORE-007 | critical | serialization | 3 | fix | Raw binary registry values cannot be JSON serialized. |
| CORE-008 | high | schema | 3 | implement | Legacy sessions lack schema/version validation. |
| CORE-009 | high | integrity | 3 | implement | Session and recovery data have no integrity validation. |
| CORE-010 | critical | rollback | 3 | redesign | Rollback is identified only by operation name and boolean result. |
| CORE-011 | critical | recovery | 3 | implement | No cancellation, crash, reboot, or incomplete-transaction recovery exists. |
| CORE-012 | high | approval | 2 | implement | No immutable plan digest or state-drift check exists. |
| CORE-013 | high | concurrency | 3 | implement | Concurrent processes can race. |
| CORE-014 | high | identity | 2 | implement | User-scoped operations do not identify intended interactive user. |
| CORE-015 | medium | events | 3 | fix | Callback failures are swallowed and callbacks are untyped. |
| CORE-016 | high | status | 3 | implement | Boolean success cannot represent partial/skipped/unsupported/reboot states. |
| CORE-017 | medium | risk model | 2 | redesign | Risk ordering relies on enum declaration and ambiguous CUSTOM semantics. |
| BAK-001 | critical | backup | 3 | redesign | Backup and engine session formats are disconnected. |
| BAK-002 | high | services | 4 | fix | Service backup records success without checking command results. |
| BAK-003 | critical | rollback | 4 | implement | Service configuration restore is absent. |
| BAK-004 | critical | rollback | 4 | implement | Scheduled-task restore is absent. |
| BAK-005 | high | integrity | 3 | fix | Checksums are never verified and use MD5. |
| BAK-006 | critical | journal | 3 | fix | Index writes are non-atomic and corruption becomes empty history. |
| BAK-007 | high | files | 4 | fix | Missing original path metadata is handled incorrectly. |
| BAK-008 | high | files | 4 | redesign | File rollback creates unmanaged `.rollback` files and can overwrite later edits. |
| BAK-009 | high | registry | 4 | redesign | Registry export/import is not exact rollback. |
| BAK-010 | high | security | 3 | implement | Backup/journal storage lacks reparse, ownership, ACL, and disk checks. |
| BAK-011 | high | security | 3 | fix | Restore-point description is interpolated into PowerShell. |
| BAK-012 | medium | retention | 7 | redesign | Age-only cleanup can delete the only recovery path. |
| BAK-013 | high | verification | 3 | implement | Recovery artifacts are not verified before mutation. |
| REG-001 | critical | registry | 4 | fix | Rollback captures target type instead of original type. |
| REG-002 | high | registry | 4 | implement | Registry view is implicit. |
| REG-003 | high | registry | 4 | implement | Writes/deletes are not read-back verified. |
| REG-004 | critical | security | 4 | redesign | Generic broad registry mutation can be exposed. |
| REG-005 | high | registry | 4 | fix | Unknown registry types default to string. |
| REG-006 | critical | rollback | 4 | fix | Visual code mutates `UserPreferencesMask` outside returned rollback. |
| CLN-001 | critical | cleanup | 4 | fix | Cleanup reports success despite deletion/permission errors. |
| CLN-002 | critical | cleanup | 4 | redesign | Irreversible cleanup is labeled SAFE and bundled broadly. |
| CLN-003 | high | cleanup | 4 | fix | Disk Cleanup and Recycle Bin return codes are ignored or errors suppressed. |
| CLN-004 | high | browsers | 4 | redesign | Browser caches assume only Default profiles and ignore running browsers. |
| CLN-005 | high | browsers | 4 | fix | Firefox cache matching yields a directory that is skipped. |
| CLN-006 | high | filesystem | 4 | fix | Cleanup `recursive` is unused and containment/reparse defense is absent. |
| CLN-007 | high | cleanup | 4 | remove | Prefetch deletion is presented as optimization. |
| CLN-008 | high | cleanup | 4 | redesign | Diagnostic/log deletion removes evidence and overlaps targets. |
| CLN-009 | medium | cleanup | 4 | fix | Analysis can double-count overlaps and cannot represent locks/not-applicable. |
| PRV-001 | critical | privacy | 4 | fix | Registry rollback ignores restoration failures and returns true. |
| PRV-002 | critical | privacy | 4 | redesign | Telemetry tasks are disabled without pre-state/rollback. |
| PRV-003 | critical | privacy | 4 | redesign | Hosts rollback replaces whole file and can erase later edits. |
| PRV-004 | high | privacy | 4 | fix | Host list contains invalid/stale entries including a port suffix. |
| PRV-005 | high | privacy | 4 | redesign | Policy behavior varies by Windows edition/build but applicability is absent. |
| PRV-006 | high | privacy | 4 | fix | Absent/protected tasks are counted as failures and output parsing is locale-dependent. |
| PRV-007 | critical | identity | 4 | fix | HKCU privacy changes may target elevated account. |
| PRV-008 | high | privacy | 4 | remove | Legacy Cortana/web-search settings are conflated and may be obsolete. |
| PRV-009 | medium | privacy | 4 | fix | DNS flush after hosts modification is unchecked. |
| STA-001 | critical | startup | 4 | fix | Startup entry can be deleted after failed destination write. |
| STA-002 | high | startup | 4 | fix | Naive `Run` replacement corrupts `RunOnce` paths. |
| STA-003 | high | startup | 4 | fix | Falsy startup values are treated as absent. |
| STA-004 | high | startup | 4 | fix | Task claims no admin while mutating HKLM startup. |
| STA-005 | critical | product | 4 | remove | Broad substring list automatically disables user-selected apps. |
| STA-006 | high | startup | 4 | fix | Scheduled-task CSV is hand-parsed and locale/quote fragile. |
| STA-007 | high | startup | 4 | fix | Rollback ignores per-item failures and returns true. |
| STA-008 | high | startup | 4 | redesign | Boot optimization comments/settings are inaccurate or obsolete. |
| STA-009 | medium | startup | 4 | fix | `get_boot_time` returns uptime, not boot duration. |
| STA-010 | medium | docs | 1 | fix | Shell-extension cleanup is advertised but absent. |
| SVC-001 | critical | services | 4 | fix | Critical-service protection is case-sensitive while Windows names are case-insensitive. |
| SVC-002 | critical | services | 4 | fix | Dependencies/dependents are queried but not enforced. |
| SVC-003 | critical | services | 4 | fix | Stop failure does not prevent disable. |
| SVC-004 | critical | gaming | 4 | fix | Gaming profile disables Xbox services. |
| SVC-005 | critical | rollback | 4 | fix | Default profile guesses Manual rather than restoring prior state. |
| SVC-006 | high | services | 4 | redesign | Hardcoded safe list ignores build, hardware, and user features. |
| SVC-007 | high | services | 4 | fix | Localized `sc` output is manually parsed and description is never read. |
| SVC-008 | high | services | 4 | implement | Exact service config and transition waiting are absent. |
| SVC-009 | medium | architecture | 2 | fix | Service manager is not integrated despite README claims. |
| NET-001 | critical | network | 4 | remove | Comments and registry settings frequently do not match. |
| NET-002 | critical | network | 4 | remove | Global `TcpAckFrequency`/`TCPNoDelay` writes are wrong-scoped. |
| NET-003 | high | network | 4 | remove | Legacy/unsupported `netsh` settings are forced. |
| NET-004 | critical | rollback | 4 | redesign | Netsh changes have no pre-state/rollback and leave partial changes. |
| NET-005 | high | network | 4 | fix | Active adapter detection through registry truthiness is fragile. |
| NET-006 | high | network | 4 | remove | DNS TTL/negative-cache changes are presented as optimization without evidence. |
| NET-007 | critical | network | 4 | remove | Network stack reset is destructive, unjournaled, and not reversible. |
| NET-008 | high | network | 4 | implement | No VPN/domain/virtual adapter/Wi-Fi/NIC topology applicability exists. |
| NET-009 | high | analysis | 4 | fix | Network analysis misinterprets registry values. |
| NET-010 | high | product | 6 | implement | No latency/jitter/throughput or game-netcode benchmark supports claims. |
| GAM-001 | critical | gaming | 4 | redesign | HAGS operation mixes Game Mode, DVR, scheduling, and HDCP changes. |
| GAM-002 | critical | gaming | 4 | remove | NVIDIA optimization changes TDR timeouts and calls them shader-cache settings. |
| GAM-003 | critical | gaming | 4 | remove | NVIDIA display container is disabled without validation/rollback. |
| GAM-004 | critical | gaming | 4 | remove | Memory operation hardcodes L2 cache and applies unsupported folklore. |
| GAM-005 | high | power | 4 | redesign | Power optimization duplicates Ultimate Performance and does not capture original. |
| GAM-006 | high | gaming | 4 | remove | Mouse/keyboard/hover preferences are treated as latency optimization. |
| GAM-007 | high | gaming | 4 | redesign | System-wide fullscreen/DWM recipes are legacy/undocumented. |
| GAM-008 | high | gaming | 6 | implement | No GPU vendor/driver/display capability detection exists. |
| GAM-009 | critical | product | 6 | implement | No per-game executable/profile/session lifecycle exists. |
| GAM-010 | high | product | 6 | implement | No benchmark supports gaming claims. |
| GAM-011 | high | product | 6 | fix | Gaming changes can disable capture despite OBS/devstream needs. |
| VIS-001 | critical | visual | 4 | fix | Performance preset discards child rollback data. |
| VIS-002 | critical | visual | 4 | remove | Hardcoded UserPreferencesMask and guessed defaults are version/user specific. |
| VIS-003 | high | visual | 4 | remove | Legacy/incorrect DWM and taskbar settings are mislabeled. |
| VIS-004 | high | accessibility | 4 | implement | Visual changes ignore accessibility and preference impact. |
| VIS-005 | high | identity | 4 | fix | HKCU visual operations have no explicit target user. |
| VIS-006 | medium | verification | 4 | implement | Visual operations do not model Explorer/logoff activation requirements. |
| SYS-001 | high | system info | 1 | fix | WMI is imported but unused and hardware data does not drive applicability. |
| SYS-002 | high | system info | 2 | implement | GPU, driver, display, battery, virtualization, domain/VPN, restore-point, and interactive-user data are missing. |
| SYS-003 | medium | privacy | 2 | fix | Reports can expose machine identifiers without redaction contract. |
| SYS-004 | medium | time | 1 | fix | Timestamps are naive and ambiguous across recovery. |
| PKG-001 | critical | testing | 1 | implement | No tests are committed. |
| PKG-002 | critical | ci | 7 | implement | No GitHub Actions or commit checks exist. |
| PKG-003 | high | dependencies | 1 | fix | pyproject and requirements disagree; runtime/dev/unused packages mix. |
| PKG-004 | high | packaging | 1 | fix | Package is named `src` and metadata has placeholders. |
| PKG-005 | high | versioning | 7 | fix | Version 1.0.0 overstates maturity. |
| PKG-006 | high | docs | 1 | fix | README advertises absent GUI/backup/restore/profiles/dirs/commands. |
| PKG-007 | high | legal | 7 | fix | MIT is declared but LICENSE absent; CONTRIBUTING referenced but absent. |
| PKG-008 | high | governance | 7 | implement | No tags/releases/branch protection/dependency alerts/code scanning. |
| SEC-001 | critical | subprocess | 3 | fix | Elevated commands rely on PATH. |
| SEC-002 | critical | injection | 3 | fix | PowerShell source interpolation permits injection. |
| SEC-003 | critical | agent boundary | 3 | implement | Generic mutation primitives could be exposed to an agent. |
| SEC-004 | critical | filesystem | 4 | implement | No canonical-path/reparse defense protects cleanup/backup. |
| SEC-005 | high | TOCTOU | 3 | implement | State can change between plan and apply. |
| SEC-006 | high | supply chain | 7 | implement | No dependency scanning, SBOM, or artifact verification. |
| TST-001 | critical | testing | 3 | implement | No fake backend or fault-injection framework exists. |
| TST-002 | critical | testing | 5 | implement | No disposable Windows VM apply/reboot/rollback proof exists. |
| TST-003 | high | testing | 3 | implement | No concurrency/crash/corruption/disk-full/locale/Unicode/reparse tests exist. |
| TST-004 | critical | testing | 5 | implement | No exact state-equality assertion exists after rollback. |
| PRD-001 | high | product | 6 | redesign | Repository is global tweak collection rather than game-profile tool. |
| PRD-002 | high | product | 6 | implement | Profiles lack schema/version/provenance/conflict/evidence. |
| PRD-003 | high | product | 6 | implement | No automatic restore after game exit/crash. |
| PRD-004 | high | product | 6 | implement | No user-readable state diff/tradeoff/evidence display. |
| PRD-005 | medium | gui | 7 | remove | GUI dependencies/commands are advertised without implementation. |
