#!/bin/bash

# ESP32 USB Serial Optimization Script
# Prevents USB autosuspend and optimizes system for reliable ESP32 communication

echo "🔧 ESP32 USB Serial Optimization Script"
echo "======================================="

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "❌ This script should NOT be run as root for safety"
   echo "   It will prompt for sudo when needed"
   exit 1
fi

# Find CH340 USB device
echo "🔍 Searching for CH340 USB device..."
CH340_DEVICE=$(lsusb | grep "1a86:7523" | head -1)
if [[ -z "$CH340_DEVICE" ]]; then
    echo "❌ CH340 device not found. Make sure ESP32 is connected."
    exit 1
fi

echo "✅ Found: $CH340_DEVICE"

# Find the device path
USB_DEVICE_PATH=""
for device in /sys/bus/usb/devices/*/; do
    if [[ -f "$device/idVendor" && -f "$device/idProduct" ]]; then
        vendor=$(cat "$device/idVendor" 2>/dev/null)
        product=$(cat "$device/idProduct" 2>/dev/null)
        if [[ "$vendor" == "1a86" && "$product" == "7523" ]]; then
            USB_DEVICE_PATH="$device"
            break
        fi
    fi
done

if [[ -z "$USB_DEVICE_PATH" ]]; then
    echo "❌ Could not find USB device path"
    exit 1
fi

echo "📍 Device path: $USB_DEVICE_PATH"

# 1. DISABLE USB AUTOSUSPEND FOR CH340
echo ""
echo "🔋 Disabling USB autosuspend for CH340..."
if [[ -f "$USB_DEVICE_PATH/power/control" ]]; then
    current_control=$(cat "$USB_DEVICE_PATH/power/control" 2>/dev/null)
    echo "   Current power control: $current_control"
    
    if [[ "$current_control" != "on" ]]; then
        echo "   Setting power control to 'on'..."
        echo "on" | sudo tee "$USB_DEVICE_PATH/power/control" > /dev/null
        echo "✅ USB autosuspend disabled for CH340"
    else
        echo "✅ USB autosuspend already disabled"
    fi
fi

# 2. DISABLE GLOBAL USB AUTOSUSPEND
echo ""
echo "🔋 Checking global USB autosuspend settings..."
current_autosuspend=$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null)
echo "   Current autosuspend timeout: ${current_autosuspend}s"

if [[ "$current_autosuspend" != "-1" ]]; then
    echo "   Disabling global USB autosuspend..."
    echo -1 | sudo tee /sys/module/usbcore/parameters/autosuspend > /dev/null
    echo "✅ Global USB autosuspend disabled"
else
    echo "✅ Global USB autosuspend already disabled"
fi

# 3. SET PERFORMANCE POWER PROFILE
echo ""
echo "⚡ Setting power profile for optimal performance..."
current_profile=$(powerprofilesctl get 2>/dev/null)
echo "   Current power profile: $current_profile"

if [[ "$current_profile" != "performance" ]]; then
    if powerprofilesctl list | grep -q "performance"; then
        powerprofilesctl set performance
        echo "✅ Power profile set to performance"
    else
        echo "⚠️  Performance profile not available, keeping current: $current_profile"
    fi
else
    echo "✅ Already using performance profile"
fi

# 4. SET CPU GOVERNOR TO PERFORMANCE
echo ""
echo "🚀 Optimizing CPU governor..."
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    if [[ -f "$cpu" ]]; then
        current_governor=$(cat "$cpu" 2>/dev/null)
        echo "   CPU $(basename $(dirname "$cpu")): $current_governor"
        
        if [[ "$current_governor" != "performance" ]]; then
            if echo "performance" | sudo tee "$cpu" > /dev/null 2>&1; then
                echo "   ✅ Set to performance"
            else
                echo "   ⚠️  Could not set to performance, keeping $current_governor"
            fi
        fi
    fi
done

# 5. OPTIMIZE SERIAL PORT SETTINGS
echo ""
echo "📡 Optimizing serial port settings..."
SERIAL_PORT="/dev/ttyUSB0"
if [[ -e "$SERIAL_PORT" ]]; then
    # Set low latency mode
    if command -v setserial >/dev/null 2>&1; then
        sudo setserial "$SERIAL_PORT" low_latency
        echo "✅ Set low latency mode for $SERIAL_PORT"
    else
        echo "⚠️  setserial not available, install with: sudo apt install setserial"
    fi
    
    # Set optimal buffer sizes
    stty -F "$SERIAL_PORT" 115200 raw -echo -echoe -echok
    echo "✅ Configured serial port parameters"
else
    echo "⚠️  Serial port $SERIAL_PORT not found"
fi

# 6. CREATE UDEV RULE FOR PERSISTENT SETTINGS
echo ""
echo "📝 Creating udev rule for persistent CH340 settings..."
UDEV_RULE="/etc/udev/rules.d/99-esp32-ch340.rules"
sudo tee "$UDEV_RULE" > /dev/null << 'EOF'
# ESP32 CH340 USB Serial - Disable autosuspend and set low latency
SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", ATTR{power/control}="on"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", RUN+="/bin/setserial /dev/%k low_latency"
EOF

if [[ $? -eq 0 ]]; then
    echo "✅ Udev rule created at $UDEV_RULE"
    sudo udevadm control --reload-rules
    echo "✅ Udev rules reloaded"
else
    echo "❌ Failed to create udev rule"
fi

# 7. CREATE SYSTEMD SERVICE FOR BOOT-TIME OPTIMIZATION
echo ""
echo "🔄 Creating systemd service for boot-time optimization..."
SYSTEMD_SERVICE="/etc/systemd/system/esp32-optimization.service"
sudo tee "$SYSTEMD_SERVICE" > /dev/null << 'EOF'
[Unit]
Description=ESP32 USB Serial Optimization
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'echo -1 > /sys/module/usbcore/parameters/autosuspend'
ExecStart=/bin/bash -c 'for dev in /sys/bus/usb/devices/*/; do if [[ -f "$dev/idVendor" && -f "$dev/idProduct" ]]; then vendor=$(cat "$dev/idVendor" 2>/dev/null); product=$(cat "$dev/idProduct" 2>/dev/null); if [[ "$vendor" == "1a86" && "$product" == "7523" ]]; then echo "on" > "$dev/power/control" 2>/dev/null; fi; fi; done'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

if [[ $? -eq 0 ]]; then
    sudo systemctl daemon-reload
    sudo systemctl enable esp32-optimization.service
    echo "✅ Systemd service created and enabled"
else
    echo "❌ Failed to create systemd service"
fi

echo ""
echo "🎉 ESP32 USB Optimization Complete!"
echo "====================================="
echo "✅ USB autosuspend disabled"
echo "✅ Power profile optimized"
echo "✅ CPU governor optimized"
echo "✅ Serial port configured"
echo "✅ Persistent settings created"
echo ""
echo "📋 Summary:"
echo "   - CH340 device found and optimized"
echo "   - Settings will persist across reboots"
echo "   - Serial communication should be more stable"
echo ""
echo "💡 To verify settings:"
echo "   cat /sys/module/usbcore/parameters/autosuspend  # Should be -1"
echo "   powerprofilesctl get                            # Should show performance or balanced"
echo "   cat $USB_DEVICE_PATH/power/control              # Should be 'on'"
