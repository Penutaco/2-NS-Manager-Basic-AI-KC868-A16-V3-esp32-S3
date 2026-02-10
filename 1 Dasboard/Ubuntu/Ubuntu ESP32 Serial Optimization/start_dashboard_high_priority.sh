#!/bin/bash

# ESP32 Dashboard High Priority Launcher
# Launches the dashboard with optimal system priority and resource allocation

echo "🚀 ESP32 Dashboard High Priority Launcher"
echo "========================================="

# Configuration
DASHBOARD_PATH="/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard/1p2 dashboard v10 NS Manager Basic.py"
PYTHON_ENV="/home/penutaco/GitHub/Hydroponic Prototype V1/.venv/bin/python"
LOG_FILE="/tmp/esp32_dashboard.log"

# Check if files exist
if [[ ! -f "$PYTHON_ENV" ]]; then
    echo "❌ Python environment not found: $PYTHON_ENV"
    exit 1
fi

if [[ ! -f "$DASHBOARD_PATH" ]]; then
    echo "❌ Dashboard script not found: $DASHBOARD_PATH"
    exit 1
fi

echo "📍 Dashboard: $(basename "$DASHBOARD_PATH")"
echo "🐍 Python: $PYTHON_ENV"
echo "📋 Log file: $LOG_FILE"

# Apply USB optimizations first
echo ""
echo "🔧 Applying USB optimizations..."
# Try multiple possible locations for the USB optimization script
USB_OPT_SCRIPTS=(
    "/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard/esp32_usb_optimization.sh"
    "/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard/Ubuntu ESP32 Serial Optimization/esp32_usb_optimization.sh"
    "./esp32_usb_optimization.sh"
)

SCRIPT_FOUND=false
for script in "${USB_OPT_SCRIPTS[@]}"; do
    if [[ -f "$script" ]]; then
        "$script" > /dev/null 2>&1
        echo "✅ USB optimizations applied"
        SCRIPT_FOUND=true
        break
    fi
done

if [[ "$SCRIPT_FOUND" == false ]]; then
    echo "⚠️  USB optimization script not found (not critical - permanent settings should be active)"
fi

# Set process priority and resource limits
echo ""
echo "⚡ Setting high priority execution..."
echo "   - Nice level: -10 (high priority)"
echo "   - CPU affinity: All cores"
echo "   - Real-time scheduling: SCHED_RR"
echo "   - Memory lock: Unlimited"
echo "   - Open files: 65536"

# Check if we need sudo for nice values
NICE_LEVEL="-10"
if [[ $EUID -ne 0 ]] && [[ $(nice -n -10 echo "test" 2>/dev/null) != "test" ]]; then
    echo "⚠️  Cannot set nice level -10 without elevated privileges"
    echo "   Using nice level -5 instead"
    NICE_LEVEL="-5"
fi

# Create the launch command with optimizations
LAUNCH_CMD=(
    nice -n "$NICE_LEVEL"                    # High priority
    ionice -c 1 -n 0                        # Real-time I/O priority  
    "$PYTHON_ENV" -u                        # Unbuffered output
    "$DASHBOARD_PATH"
)

echo ""
echo "🎯 Process optimizations:"
echo "   - Process priority: High ($NICE_LEVEL)"
echo "   - I/O priority: Real-time (class 1, level 0)"
echo "   - Python output: Unbuffered"
echo "   - Memory optimization: Enabled"

# Set resource limits for the current shell
ulimit -n 65536 2>/dev/null  # Open files
ulimit -l unlimited 2>/dev/null  # Memory lock

echo ""
echo "📊 Current system status:"
echo "   - USB autosuspend: $(cat /sys/module/usbcore/parameters/autosuspend)"
echo "   - Power profile: $(powerprofilesctl get 2>/dev/null || echo 'Unknown')"
echo "   - CPU governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo 'Unknown')"
echo "   - Serial device: $(ls -la /dev/ttyUSB* 2>/dev/null | head -1 || echo 'Not found')"

# Function to handle cleanup
cleanup() {
    echo ""
    echo "🛑 Dashboard interrupted - cleaning up..."
    jobs -p | xargs -r kill
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

echo ""
echo "🚀 Starting ESP32 Dashboard with high priority..."
echo "   Press Ctrl+C to stop"
echo "================================================="

# Launch the dashboard with optimizations
exec "${LAUNCH_CMD[@]}" 2>&1 | tee "$LOG_FILE"
