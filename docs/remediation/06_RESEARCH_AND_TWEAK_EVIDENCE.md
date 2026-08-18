# 06 — Research and Tweak Evidence

## Rule

No Windows tweak is accepted because it appears in the legacy repository or in optimization guides. Every retained operation has an evidence record.

## Evidence fields

```text
operation_id
claim
authoritative_sources
source_access_dates
supported_os_editions
supported_os_build_range
supported_architectures
hardware_or_driver_prerequisites
observed_effect
known_tradeoffs
reboot_or_logoff_behavior
verification_method
rollback_method
benchmark_protocol
default_disposition
```

## Source hierarchy

1. Current Microsoft Learn, Windows SDK/WDK, or official support documentation.
2. Official GPU, chipset, NIC, game, or platform vendor documentation.
3. Primary technical research or reproducible controlled experiments.
4. Community material only as a hypothesis source.

Optimization blogs are not proof that a registry key is valid or beneficial.

## Legacy behavior requiring removal/quarantine unless proven

Independently evaluate:

- blanket prefetch deletion
- blanket Windows log deletion
- global `TcpAckFrequency` and `TCPNoDelay`
- broad TCP registry bundles
- unsupported `netsh` chimney/DCA/congestion commands
- blanket ECN enablement
- `NetworkThrottlingIndex` and `SystemResponsiveness` claims
- hardcoded `SecondLevelDataCache=256`
- `DisablePagingExecutive` as performance/boot optimization
- memory-compression registry claims
- TDR timeout changes labeled shader-cache optimization
- HDCP-related driver registry edits
- disabling `NVDisplay.ContainerLocalSystem`
- system-wide fullscreen-optimization recipes
- undocumented DWM environment variables
- hardcoded `UserPreferencesMask`
- guessed Windows defaults
- telemetry hosts-file blocklists
- service “safe to disable” lists
- setting every service to Manual as restore
- disabling Xbox services in a gaming profile
- global mouse/keyboard preference changes
- automatic High/Ultimate Performance on every machine
- disabling Game DVR where recording/OBS is needed

## Disposition standard

- **Default:** authoritative support and measured target-workload benefit.
- **Optional:** legitimate preference/tradeoff, clearly explained.
- **Experimental:** plausible but unproven; opt-in and disposable-environment warning.
- **Removed:** unsupported, obsolete, misleading, dangerous, or no measurable value.

Removal is a successful remediation, not missing work.
