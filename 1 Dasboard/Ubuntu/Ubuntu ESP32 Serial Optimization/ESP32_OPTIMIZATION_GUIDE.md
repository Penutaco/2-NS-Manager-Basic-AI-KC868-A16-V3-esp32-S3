# ESP32 USB Serial Communication Optimization Guide

## 🎯 Problem Solved
- **USB Serial Port Changes**: Due to power management causing disconnections
- **Low Priority Process**: Dashboard not getting sufficient system resources
- **Energy Management**: System suspending USB devices to save power

## ✅ Optimizations Applied

### 1. USB Power Management
- **Global USB Autosuspend**: Disabled (`-1` = never suspend)
- **CH340 Specific**: Power control set to `on` (never suspend)
- **Persistent Settings**: Udev rules and systemd services created
- **Low Latency Mode**: Serial port configured for minimal delay

### 2. System Performance
- **CPU Governor**: Set to `performance` for maximum responsiveness  
- **Process Priority**: Dashboard runs with high priority (`nice -10`)
- **I/O Priority**: Real-time I/O scheduling (`ionice -c 1 -n 0`)
- **Resource Limits**: Increased file descriptors and memory limits

### 3. Serial Port Optimization
- **Low Latency**: `setserial /dev/ttyUSB0 low_latency`
- **Optimal Parameters**: 115200 baud, raw mode, no echo
- **Buffer Optimization**: Unbuffered Python output

### 4. Message Filtering
- **Spam Reduction**: Filters out calculation spam messages
- **Important Events**: Preserves coefficient updates, dosing actions, PRG events
- **Performance**: Filtering happens early to reduce processing load

## 📁 Files Created

### Optimization Scripts
- `esp32_usb_optimization.sh` - Main optimization script
- `start_dashboard_high_priority.sh` - High priority dashboard launcher
- `esp32_usb_monitor.sh` - Connection monitoring and recovery

### System Files (Auto-created)
- `/etc/udev/rules.d/99-esp32-ch340.rules` - Persistent USB settings
- `/etc/systemd/system/esp32-optimization.service` - Boot-time optimization

## 🚀 Usage Instructions

### Method 1: High Priority Launcher (Recommended)
```bash
cd "/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard"
./start_dashboard_high_priority.sh
```

### Method 2: Manual Optimization + Normal Launch
```bash
./esp32_usb_optimization.sh
"/home/penutaco/GitHub/Hydroponic Prototype V1/.venv/bin/python" "/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard/1p2 dashboard v10 NS Manager Basic.py"
```

### Method 3: Background USB Monitor
```bash
# Run in background to monitor and auto-recover USB connection
nohup ./esp32_usb_monitor.sh &
```

## 🔍 Verification Commands

Check if optimizations are active:
```bash
# USB autosuspend (should be -1)
cat /sys/module/usbcore/parameters/autosuspend

# CH340 power control (should be 'on')
cat /sys/bus/usb/devices/2-3/power/control

# CPU governor (should be 'performance')
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Serial port exists and accessible
ls -la /dev/ttyUSB0

# Check if filtering is working (look for filter count messages)
tail -f /tmp/esp32_dashboard.log
```

## 📊 Expected Results

### Before Optimization
- ❌ USB disconnections every few minutes
- ❌ Serial port changing (ttyUSB0 → ttyUSB1)
- ❌ Dashboard running at normal priority
- ❌ Calculation spam flooding the log

### After Optimization
- ✅ Stable USB connection
- ✅ Consistent serial port (`/dev/ttyUSB0`)
- ✅ High priority dashboard process
- ✅ Clean event log with important events only
- ✅ Better system responsiveness
- ✅ Auto-recovery if connection fails

## 🔧 Troubleshooting

### If USB still disconnects:
1. Check if optimizations are active using verification commands
2. Run USB monitor: `./esp32_usb_monitor.sh`
3. Check system logs: `journalctl -f | grep -i usb`

### If dashboard seems slow:
1. Verify process priority: `ps aux | grep dashboard`
2. Check CPU governor: `cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`
3. Use the high priority launcher

### If filtering isn't working:
1. Look for filter messages: `🔇 Filtered X calculation spam messages`
2. Check the dashboard log: `tail -f /tmp/esp32_dashboard.log`

## 🔄 Persistence

All optimizations persist across reboots thanks to:
- **Systemd service**: `esp32-optimization.service`
- **Udev rules**: `/etc/udev/rules.d/99-esp32-ch340.rules`
- **Boot-time scripts**: Automatically apply USB settings

## 💡 Additional Tips

1. **Always use the high priority launcher** for best performance
2. **Monitor the log files** to verify filtering is working  
3. **Check system status** periodically with verification commands
4. **Consider running USB monitor** in background for auto-recovery
5. **If issues persist**, check hardware (USB cable, ESP32, USB port)
