# Dashboard Watchdog - External Process Monitor

## Overview

The Dashboard Watchdog is an external monitoring program that ensures the hydroponic dashboard stays running and receiving data. When the dashboard stops receiving ESP32 data, the watchdog automatically kills and restarts the entire dashboard process.

## Features

- ✅ **External Process Monitoring** - Runs independently of the dashboard
- ✅ **Data Freshness Detection** - Monitors CSV file timestamps for recent data
- ✅ **Automatic Restart** - Kills and restarts stuck dashboard processes
- ✅ **Rate Limiting** - Prevents restart loops with configurable limits
- ✅ **High-Priority Startup** - Uses optimized startup scripts
- ✅ **Systemd Integration** - Runs as a Linux service
- ✅ **Comprehensive Logging** - Detailed logs for troubleshooting
- ✅ **Configurable** - Easy configuration via INI file

## Quick Start

### 1. Install and Setup
```bash
cd "/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard"
./watchdog_manager.sh install
```

### 2. Start the Watchdog
```bash
./watchdog_manager.sh start
```

### 3. Check Status
```bash
./watchdog_manager.sh status
```

## Management Commands

The `watchdog_manager.sh` script provides easy management:

```bash
# Install dependencies and systemd service
./watchdog_manager.sh install

# Start the watchdog
./watchdog_manager.sh start

# Stop the watchdog
./watchdog_manager.sh stop

# Restart the watchdog
./watchdog_manager.sh restart

# Check service status
./watchdog_manager.sh status

# View logs
./watchdog_manager.sh logs

# Test run manually (foreground)
./watchdog_manager.sh test

# Uninstall service
./watchdog_manager.sh uninstall
```

## How It Works

### Health Detection
The watchdog monitors dashboard health by checking:

1. **CSV File Freshness** - Monitors `/data/hydroponic_data.csv` modification time
2. **Process Status** - Ensures dashboard process is running and responsive
3. **Configurable Timeout** - Default 5 minutes without new data = unhealthy

### Restart Process
When dashboard is unhealthy:

1. **Kill Process** - Uses `pkill -f` to terminate dashboard
2. **Cleanup Wait** - Allows 2 seconds for graceful shutdown
3. **Start Fresh** - Launches new dashboard instance
4. **Verify Startup** - Confirms new process started successfully
5. **Rate Limiting** - Prevents excessive restarts

### Rate Limiting
- **Maximum 6 restarts per hour** (configurable)
- **Minimum 10 minutes between restarts**
- **Automatic counter reset** every hour

## Configuration

Edit `watchdog_config.ini` to customize behavior:

### Key Settings

```ini
[MONITORING]
data_timeout_minutes = 5          # Data timeout threshold
check_interval_seconds = 30       # How often to check health
max_restarts_per_hour = 6         # Restart rate limit

[DASHBOARD]
use_startup_script = true         # Use high-priority startup
script_path = /path/to/dashboard  # Dashboard script location

[LOGGING]
log_level = INFO                  # Logging verbosity
log_file = dashboard_watchdog.log # Log file location
```

## Monitoring Data Sources

The watchdog can monitor multiple indicators:

1. **CSV File Monitoring** (Primary)
   - Monitors file modification time
   - Most reliable method for data freshness

2. **Process Monitoring** (Secondary)
   - Checks if dashboard process exists
   - Detects zombie/defunct processes

3. **Future Enhancements**
   - ZMQ heartbeat monitoring
   - Log file pattern matching
   - Health status files

## Logging

The watchdog provides comprehensive logging:

### Log Levels
- **INFO** - Normal operations, restarts
- **WARNING** - Health issues, rate limiting
- **ERROR** - Restart failures, critical issues
- **DEBUG** - Detailed health check info

### Log Locations
- **File**: `dashboard_watchdog.log`
- **Systemd**: `sudo journalctl -u dashboard-watchdog.service -f`

### Example Log Output
```
2025-09-07 10:15:30 - INFO - 🐕 Dashboard Watchdog starting...
2025-09-07 10:15:30 - INFO - Dashboard process found, monitoring existing instance
2025-09-07 10:16:00 - DEBUG - Dashboard healthy ✅
2025-09-07 10:20:30 - WARNING - CSV file not updated for 310.2s - UNHEALTHY
2025-09-07 10:20:30 - WARNING - 🚨 Dashboard unhealthy, attempting restart...
2025-09-07 10:20:30 - INFO - 🔄 RESTARTING DASHBOARD (attempt 1/6)
2025-09-07 10:20:32 - INFO - Dashboard process killed successfully
2025-09-07 10:20:42 - INFO - Dashboard started successfully
2025-09-07 10:20:42 - INFO - ✅ Dashboard restart completed successfully
```

## Troubleshooting

### Common Issues

**Watchdog not starting:**
```bash
# Check service status
./watchdog_manager.sh status

# View detailed logs
./watchdog_manager.sh logs

# Test manually
./watchdog_manager.sh test
```

**Dashboard not restarting:**
```bash
# Check file permissions
ls -la dashboard_watchdog.py
ls -la watchdog_config.ini

# Verify startup script exists
ls -la "Ubuntu ESP32 Serial Optimization/start_dashboard_high_priority.sh"

# Check Python dependencies
pip3 list | grep psutil
```

**Too many restarts:**
```bash
# Check restart rate limits in config
cat watchdog_config.ini | grep max_restarts

# View restart history in logs
./watchdog_manager.sh logs | grep "RESTARTING DASHBOARD"
```

### Manual Testing

Test the watchdog manually to debug issues:

```bash
# Run in foreground to see output
./watchdog_manager.sh test

# Check specific health indicators
python3 -c "
from dashboard_watchdog import DashboardWatchdog
w = DashboardWatchdog()
print('Healthy:', w.is_dashboard_healthy())
print('Process:', w.find_dashboard_process())
"
```

## System Integration

### Systemd Service
The watchdog runs as a systemd service with:
- **Automatic startup** on boot
- **Automatic restart** if watchdog crashes
- **Proper logging** via journald
- **Service management** via systemctl

### Security
- Runs as user `penutaco` (not root)
- Uses `sudo` only for dashboard startup script
- Limited filesystem access
- No new privileges

## Comparison with Internal Health Monitor

| Feature | Internal Monitor | External Watchdog |
|---------|------------------|-------------------|
| **Detection** | ✅ Good | ✅ Good |
| **Restart Capability** | ❌ Limited | ✅ Complete |
| **Independence** | ❌ Same process | ✅ Separate process |
| **Reliability** | ❌ Can get stuck | ✅ Always works |
| **Rate Limiting** | ❌ Basic | ✅ Advanced |
| **Service Integration** | ❌ None | ✅ Systemd |

## Files Overview

- `dashboard_watchdog.py` - Main watchdog program
- `watchdog_config.ini` - Configuration file  
- `watchdog_manager.sh` - Management script
- `dashboard-watchdog.service` - Systemd service file
- `WATCHDOG_README.md` - This documentation

## Why This Approach Works

The external watchdog solves the fundamental problem where the dashboard's internal health monitor gets stuck in the same bugs that cause the connection issues. By running as a completely separate process, the watchdog can:

1. **Always detect problems** - Not affected by dashboard bugs
2. **Always restart successfully** - Complete process replacement
3. **Prevent endless loops** - Rate limiting and proper exit conditions
4. **Provide reliable monitoring** - Independent health assessment

This is the same pattern used by production systems worldwide for ensuring service reliability.
