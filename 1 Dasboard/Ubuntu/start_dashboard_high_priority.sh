#!/bin/bash

# High-Priority ESP32 Dashboard Launcher
# This script runs the dashboard with elevated priority for stable serial communication

echo "🚀 Starting ESP32 Dashboard with high priority..."

# Navigate to dashboard directory
cd "/Users/penutaco/Desktop/Hydroponic Prototype/Hydroponic-Prototype-V1/0 Dasboard"

# Check if ESP32 is connected
ESP32_DEVICE="/dev/cu.usbserial-10"
if [ ! -e "$ESP32_DEVICE" ]; then
    echo "❌ ESP32 device not found at $ESP32_DEVICE"
    echo "Please check USB connection and try again."
    exit 1
fi

echo "✅ ESP32 device found at $ESP32_DEVICE"

# Set device permissions
sudo chmod 666 "$ESP32_DEVICE"

# Check if dashboard is already running
EXISTING_PID=$(ps aux | grep "1p2 dashboard v10.py" | grep -v grep | awk '{print $2}' | head -1)
if [ -n "$EXISTING_PID" ]; then
    echo "⚠️  Dashboard already running with PID $EXISTING_PID"
    echo "Stopping existing dashboard..."
    kill $EXISTING_PID
    sleep 2
fi

# Run dashboard with high priority and specific nice value
echo "🔧 Starting dashboard with elevated priority..."
echo "📊 Dashboard will run with priority -10 (higher priority)"

# Use sudo to set high priority (-10) and run dashboard
sudo nice -n -10 python3 "1p2 dashboard v10.py" &

DASHBOARD_PID=$!
echo "✅ Dashboard started with PID $DASHBOARD_PID and high priority"

# Monitor for a few seconds to ensure it starts properly
sleep 5

if ps -p $DASHBOARD_PID > /dev/null; then
    echo "✅ Dashboard is running successfully with high priority"
    echo "💡 Serial communication should be more stable now"
    echo "📊 Monitor the dashboard logs for any issues"
else
    echo "❌ Dashboard failed to start properly"
    echo "Check the terminal output for error messages"
fi

echo ""
echo "🔍 Current dashboard processes:"
ps aux | grep "dashboard" | grep -v grep
