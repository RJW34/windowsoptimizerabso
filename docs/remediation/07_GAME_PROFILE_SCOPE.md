# 07 — Game Profile Scope

## Objective

Build a conservative, measurable per-game optimization system rather than a global registry-tweak launcher.

First profiles:

- `rivals-of-aether-2`
- `slippi-melee`

## Session behavior

Prefer:

1. inspect
2. capture state
3. apply approved settings immediately before launch
4. verify
5. monitor the exact game process
6. restore on normal exit
7. recover/restore after tool or game crash/reboot

Persistent changes require a separate explicit plan.

## Rivals of Aether 2

Consider without assuming a universal answer:

- executable discovery/version
- fullscreen/borderless behavior
- monitor refresh
- GPU vendor/driver
- HAGS support and measured effect
- desktop versus laptop power
- shader/cache behavior
- controller/input stack
- audio services
- OBS/capture compatibility
- Special K only when explicitly selected and supported
- anti-cheat/online restrictions
- frame-time benchmark and regression budget

Do not change global mouse sensitivity or disable core NVIDIA display services.

## Slippi

Consider:

- Dolphin/Slippi executable/version
- rendering backend/GPU
- controller adapter/driver
- audio latency/stability
- monitor refresh/presentation
- network conditions for rollback netplay
- process priority only if supported and measured
- OBS/capture preservation
- emulator configuration ownership
- input/frame-time instrumentation

Do not apply generic TCP folklore. Network changes need measured rollback-netplay evidence and adapter-specific applicability.

## Profile constraints

A profile selects only allowlisted operation IDs and constrained parameters. It cannot contain arbitrary registry paths, service/task names, PowerShell, commands, or deletion roots.

Profiles are versioned and signed or bundled from a trusted source before automated use.

## Benchmark decision

For each proposed performance operation:

- establish repeated baseline
- apply the isolated operation or controlled group
- repeat comparably
- measure central tendency and variance
- check stability, power, capture, audio, network, and UX regressions
- retain only when benefit exceeds a defined threshold or it is an explicit preference

A profile may contain zero system tweaks when defaults are best.
