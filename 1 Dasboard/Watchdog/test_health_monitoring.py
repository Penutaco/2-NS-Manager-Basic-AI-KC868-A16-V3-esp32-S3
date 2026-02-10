#!/usr/bin/env python3
"""
Test script for health monitoring functionality
"""

import time
import glob
import serial
from datetime import datetime

# Configuration for testing
BAUD_RATE = 115200
PORT_SCAN_PATTERN = '/dev/ttyUSB*'

# Test variables
connection_status_log = []

def log_connection_status(message, level="INFO"):
    """Log connection status messages with timestamps"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    status_entry = f"[{timestamp}] {level}: {message}"
    connection_status_log.append(status_entry)
    
    # Print with appropriate emoji
    emoji_map = {
        "INFO": "ℹ️",
        "SUCCESS": "✅", 
        "WARNING": "⚠️",
        "ERROR": "❌",
        "RECOVERY": "🔍"
    }
    print(f"{emoji_map.get(level, 'ℹ️')} {status_entry}")

def scan_for_esp32_ports():
    """Scan for available USB ports that might have the ESP32"""
    try:
        available_ports = glob.glob(PORT_SCAN_PATTERN)
        available_ports.sort()  # Sort for consistent ordering
        
        log_connection_status(f"Scanning USB ports: {available_ports}", "RECOVERY")
        
        for port in available_ports:
            if test_port_connection(port):
                return port
        
        return None
    except Exception as e:
        log_connection_status(f"Error scanning ports: {e}", "ERROR")
        return None

def test_port_connection(port, timeout=3):
    """Test if a specific port has the ESP32 responding"""
    try:
        log_connection_status(f"Testing connection to {port}", "RECOVERY")
        
        with serial.Serial(port, BAUD_RATE, timeout=timeout) as ser:
            ser.reset_input_buffer()
            time.sleep(1)  # Give time for any initial data
            
            # Check if we receive any data that looks like ESP32 output
            start_time = time.time()
            while time.time() - start_time < timeout:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line and (',' in line or 'SENSOR' in line or 'EVENT' in line):
                        log_connection_status(f"ESP32 detected on {port}", "SUCCESS")
                        return True
                time.sleep(0.1)
            
        log_connection_status(f"No ESP32 response from {port}", "WARNING")
        return False
        
    except Exception as e:
        log_connection_status(f"Failed to test {port}: {e}", "WARNING")
        return False

def main():
    print("🧪 Testing Health Monitoring System")
    print("=" * 50)
    
    log_connection_status("Health monitoring test started", "INFO")
    
    # Test 1: Port scanning
    print("\n📋 Test 1: Scanning for ESP32 ports")
    esp32_port = scan_for_esp32_ports()
    
    if esp32_port:
        log_connection_status(f"ESP32 found on {esp32_port}", "SUCCESS")
        
        # Test 2: Connection test
        print(f"\n📋 Test 2: Testing connection to {esp32_port}")
        if test_port_connection(esp32_port, timeout=5):
            log_connection_status("Connection test successful", "SUCCESS")
        else:
            log_connection_status("Connection test failed", "ERROR")
    else:
        log_connection_status("No ESP32 found on any USB port", "ERROR")
    
    # Display connection log
    print("\n📋 Connection Status Log:")
    print("-" * 30)
    for entry in connection_status_log:
        print(entry)
    
    print("\n✅ Health monitoring test completed")

if __name__ == "__main__":
    main()
