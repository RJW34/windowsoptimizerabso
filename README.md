# Windows Optimizer Absolute (WindowsOptimizerAbso)

> ## ⚠ PRE-ALPHA — NOT SAFE TO RUN ON A MACHINE YOU CARE ABOUT
>
> This repository is under active remediation following an audit that found the safety claims to
> be substantially ahead of the implementation: rollback was a no-op that printed success, mutating
> operations captured no exact pre-state, and there was no transaction journal, no test suite and
> no CI.
>
> **All mutating commands are currently disabled.** Read-only inspection works. The remediation
> plan, the full defect register and the current status are in
> [`docs/remediation/`](docs/remediation/) — start with
> [`WORK_LEDGER.md`](docs/remediation/WORK_LEDGER.md).
>
> Do not run this against a production or personal Windows install. Use a disposable VM or
> Windows Sandbox.

A comprehensive Windows optimization toolkit designed for power users who want full control over their system's performance, privacy, and resource management.

## Features

### System Cleanup
- Temporary file removal (Windows Temp, User Temp, Browser caches)
- Windows Update cleanup
- Recycle Bin management
- Thumbnail cache clearing
- Log file cleanup
- Prefetch optimization

### Privacy & Telemetry Control
- Disable Windows telemetry and data collection
- Manage Cortana and search indexing
- Control advertising ID and personalization
- Block telemetry hosts via hosts file
- Scheduled tasks audit and cleanup

### Service Management
- Disable unnecessary Windows services
- Service presets (Gaming, Workstation, Minimal, Default)
- Safe service recommendations with rollback capability
- Dependency-aware service management

### Startup Optimization
- Startup program management
- Scheduled task audit
- Boot time analysis
- Shell extension cleanup

### Registry Optimization
- Registry cleanup and defragmentation
- Invalid entry removal
- Orphaned key detection
- Registry backup and restore

### Network Optimization
- TCP/IP stack optimization
- DNS cache management
- Network adapter tuning
- Bandwidth optimization tweaks

### Gaming & Performance
- Game Mode optimization
- GPU scheduling tweaks
- Power plan optimization
- Visual effects management
- Memory optimization
- Process priority management

### Backup & Restore
- Full system state backup before changes
- Individual module rollback
- Registry backup/restore
- Service configuration snapshots

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/windowsoptimizerabso.git
cd windowsoptimizerabso

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m src.main
```

## Requirements

- Windows 10/11
- Python 3.10+
- Administrator privileges (for most operations)

## Usage

### GUI Mode
```bash
python -m src.main --gui
```

### CLI Mode
```bash
# Run all safe optimizations
python -m src.main --optimize all

# Run specific module
python -m src.main --module privacy

# Create system backup
python -m src.main --backup

# Restore from backup
python -m src.main --restore <backup_id>

# Analyze system without making changes
python -m src.main --analyze
```

### Preset Profiles
```bash
# Gaming profile - maximum performance
python -m src.main --profile gaming

# Workstation profile - balanced
python -m src.main --profile workstation

# Minimal profile - maximum privacy, minimal services
python -m src.main --profile minimal

# Default profile - restore Windows defaults
python -m src.main --profile default
```

## Safety Features

- **Dry Run Mode**: Preview changes before applying
- **Automatic Backups**: System state saved before modifications
- **Rollback Support**: Undo any changes made
- **Safe Defaults**: Conservative defaults, aggressive options opt-in
- **Dependency Checking**: Won't disable services that others depend on

## Project Structure

```
windowsoptimizerabso/
├── src/
│   ├── core/           # Core engine and utilities
│   ├── modules/        # Optimization modules
│   ├── gui/            # GUI components
│   └── utils/          # Helper utilities
├── tests/              # Unit and integration tests
├── docs/               # Documentation
├── config/             # Configuration files and presets
└── scripts/            # Standalone scripts
```

## Contributing

Contributions welcome! Please read CONTRIBUTING.md first.

## Disclaimer

This software modifies system settings. While safety measures are in place, use at your own risk. Always maintain backups of important data.

## License

MIT License - See LICENSE for details
