# Storage Health Check Tool

A standalone executable tool for performing read-only health checks on enterprise storage platforms. Built in Python and packaged as a single EXE file that runs without requiring Python on the target system.

## Features

- **Platform Support**: Pure Storage and NetApp ONTAP
- **Interactive CLI**: User-friendly menu-driven interface
- **Secure Authentication**: Runtime credential input with hidden password entry
- **Read-Only Operations**: Safe for production environments
- **Comprehensive Checks**: Array/cluster health, capacity usage, hardware status, and component states
- **Structured Output**: JSON reports with normalized health data
- **Offline Operation**: No internet connectivity required
- **Graceful Failure**: Continues operation even if individual platforms fail

## Health Checks Performed

### Pure Storage
- Array operational state
- Capacity usage with thresholds (80% warning, 95% critical)
- Hardware component health status

### NetApp ONTAP
- Cluster health status
- Node health status
- Aggregate state
- Volume state

## Output Format

Each health check produces a normalized record with:
- Platform
- Component
- Check name
- Value
- Status (OK/WARNING/CRITICAL)
- Recommended action (when applicable)

## Usage

1. Run the executable: `storage_health_check.exe`
2. Select storage platform from the menu
3. Enter management IP/hostname
4. Provide API credentials (username/password)
5. View results on console
6. JSON report is automatically saved

## Building the EXE

Requirements:
- Python 3.8+
- PyInstaller

```bash
pip install -r requirements.txt
pyinstaller --onefile --windowed storage_health_check.py
```

## Security Notes

- Credentials are never stored on disk
- All API calls are read-only
- SSL certificate verification is disabled for customer environments
- No data is transmitted externally

## Requirements

- requests
- urllib3

## License

[Add license information]