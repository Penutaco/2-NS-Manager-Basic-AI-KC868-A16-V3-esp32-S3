#!/bin/bash

# Quick ESP32 Status Check
echo "🔍 ESP32 System Status Check"
echo "============================"

echo ""
echo "🔄 PERMANENT SETTINGS (Applied at boot):"
echo "   USB autosuspend: $(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo 'Unknown')"

# Check CH340 device
for device in /sys/bus/usb/devices/*/; do
    if [[ -f "$device/idVendor" && -f "$device/idProduct" ]]; then
        vendor=$(cat "$device/idVendor" 2>/dev/null)
        product=$(cat "$device/idProduct" 2>/dev/null)
        if [[ "$vendor" == "1a86" && "$product" == "7523" ]]; then
            power_control=$(cat "$device/power/control" 2>/dev/null)
            echo "   CH340 power control: $power_control"
            break
        fi
    fi
done

echo ""
echo "⚡ DYNAMIC SETTINGS (May change):"
echo "   CPU governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo 'Unknown')"
echo "   Power profile: $(powerprofilesctl get 2>/dev/null || echo 'Unknown')"

echo ""
echo "📡 SERIAL PORT:"
if [[ -e "/dev/ttyUSB0" ]]; then
    echo "   ✅ /dev/ttyUSB0 exists and accessible"
    echo "   Permissions: $(ls -l /dev/ttyUSB0 | cut -d' ' -f1,3,4)"
else
    echo "   ❌ /dev/ttyUSB0 not found"
fi

echo ""
echo "🎯 RECOMMENDATION:"
if [[ $(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null) == "-1" ]]; then
    echo "   ✅ Core optimizations are permanent"
    echo "   ✅ You can run dashboard normally:"
    echo "   '/home/penutaco/GitHub/Hydroponic Prototype V1/.venv/bin/python' '/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard/1p2 dashboard v10 NS Manager Basic.py'"
    echo ""
    echo "   💡 For maximum performance, optionally use:"
    echo "   './start_dashboard_high_priority.sh'"
else
    echo "   ⚠️  Core optimizations not active, run:"
    echo "   './esp32_usb_optimization.sh' (one time)"
fi
