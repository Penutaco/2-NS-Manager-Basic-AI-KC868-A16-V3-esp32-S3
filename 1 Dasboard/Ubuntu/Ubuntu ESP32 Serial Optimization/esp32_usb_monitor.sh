#!/bin/bash

# ESP32 USB Connection Monitor
# Monitors the ESP32 USB connection and resets it if it becomes unstable

USB_DEVICE_VENDOR="1a86"
USB_DEVICE_PRODUCT="7523"
SERIAL_PORT="/dev/ttyUSB0"
CHECK_INTERVAL=30  # seconds
LOG_FILE="/tmp/esp32_usb_monitor.log"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

check_usb_device() {
    lsusb | grep -q "$USB_DEVICE_VENDOR:$USB_DEVICE_PRODUCT"
}

check_serial_port() {
    [[ -e "$SERIAL_PORT" ]] && [[ -r "$SERIAL_PORT" ]] && [[ -w "$SERIAL_PORT" ]]
}

reset_usb_device() {
    log_message "🔄 Attempting to reset USB device..."
    
    # Find the USB device path
    for device in /sys/bus/usb/devices/*/; do
        if [[ -f "$device/idVendor" && -f "$device/idProduct" ]]; then
            vendor=$(cat "$device/idVendor" 2>/dev/null)
            product=$(cat "$device/idProduct" 2>/dev/null)
            if [[ "$vendor" == "$USB_DEVICE_VENDOR" && "$product" == "$USB_DEVICE_PRODUCT" ]]; then
                device_path="$device"
                break
            fi
        fi
    done
    
    if [[ -n "$device_path" ]]; then
        # Disable and re-enable the device
        echo 0 > "$device_path/authorized" 2>/dev/null
        sleep 2
        echo 1 > "$device_path/authorized" 2>/dev/null
        sleep 3
        
        # Reapply optimizations
        echo "on" > "$device_path/power/control" 2>/dev/null
        if command -v setserial >/dev/null 2>&1 && [[ -e "$SERIAL_PORT" ]]; then
            setserial "$SERIAL_PORT" low_latency 2>/dev/null
        fi
        
        log_message "✅ USB device reset completed"
    else
        log_message "❌ Could not find USB device path for reset"
    fi
}

log_message "🔍 ESP32 USB Connection Monitor started"
log_message "   Monitoring: $USB_DEVICE_VENDOR:$USB_DEVICE_PRODUCT"
log_message "   Serial port: $SERIAL_PORT"
log_message "   Check interval: ${CHECK_INTERVAL}s"

consecutive_failures=0
max_failures=3

while true; do
    usb_ok=false
    serial_ok=false
    
    if check_usb_device; then
        usb_ok=true
    fi
    
    if check_serial_port; then
        serial_ok=true
    fi
    
    if [[ "$usb_ok" == true && "$serial_ok" == true ]]; then
        if [[ $consecutive_failures -gt 0 ]]; then
            log_message "✅ Connection restored after $consecutive_failures failures"
        fi
        consecutive_failures=0
    else
        consecutive_failures=$((consecutive_failures + 1))
        log_message "⚠️  Connection issue detected (failure $consecutive_failures/$max_failures)"
        log_message "   USB device present: $usb_ok"
        log_message "   Serial port accessible: $serial_ok"
        
        if [[ $consecutive_failures -ge $max_failures ]]; then
            log_message "❌ Max failures reached, attempting USB reset..."
            reset_usb_device
            consecutive_failures=0
            sleep 10  # Extra wait after reset
        fi
    fi
    
    sleep "$CHECK_INTERVAL"
done
