#!/usr/bin/env python3
"""
Simple test script to verify subprocess restart functionality
This tests the core mechanics without requiring the full dashboard
"""

import threading
import subprocess
import time
import signal
import sys

# Test variables similar to main script
current_serial_port = '/dev/ttyUSB1'
restart_subprocess_flag = threading.Event()
current_process = None

def mock_health_monitor():
    """Mock health monitor that triggers port change"""
    global current_serial_port, restart_subprocess_flag
    
    print("🔍 Mock health monitor started")
    time.sleep(5)  # Wait 5 seconds
    
    # Simulate port change detection
    print("⚠️ Simulating port change from /dev/ttyUSB1 to /dev/ttyUSB0")
    current_serial_port = '/dev/ttyUSB0'
    restart_subprocess_flag.set()
    print("✅ Restart signal sent")

def mock_data_reader():
    """Mock data reader that handles subprocess restart"""
    global current_process, restart_subprocess_flag, current_serial_port
    
    print("📊 Starting mock data reader...")
    
    # Start initial subprocess (using 'sleep' command as mock)
    current_process = subprocess.Popen(['sleep', '30'], stdout=subprocess.PIPE)
    print(f"🚀 Initial subprocess started (PID: {current_process.pid})")
    
    iteration = 0
    while iteration < 20:  # Run for limited time in test
        # Check if restart was requested
        if restart_subprocess_flag.is_set():
            print(f"🔄 Restart requested! Restarting with port: {current_serial_port}")
            
            # Close current process
            if current_process:
                try:
                    current_process.terminate()
                    current_process.wait(timeout=2)
                    print(f"✅ Old subprocess terminated (PID was: {current_process.pid})")
                except subprocess.TimeoutExpired:
                    print("⚠️ Process termination timeout, killing forcefully")
                    current_process.kill()
                    current_process.wait()
                except Exception as e:
                    print(f"❌ Error terminating process: {e}")
            
            # Start new process
            try:
                current_process = subprocess.Popen(['sleep', '30'], stdout=subprocess.PIPE)
                print(f"🚀 New subprocess started (PID: {current_process.pid}) for port {current_serial_port}")
                
                # Clear the restart flag
                restart_subprocess_flag.clear()
                print("✅ Restart completed successfully")
                
            except Exception as e:
                print(f"❌ Failed to restart subprocess: {e}")
                restart_subprocess_flag.clear()
                break
        
        # Simulate normal processing
        print(f"📊 Processing iteration {iteration + 1}/20...")
        time.sleep(1)
        iteration += 1
    
    # Cleanup
    if current_process:
        current_process.terminate()
        current_process.wait()
        print("🧹 Test cleanup completed")

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\n🛑 Test interrupted by user")
    if current_process:
        current_process.terminate()
        current_process.wait()
    sys.exit(0)

if __name__ == "__main__":
    print("🧪 Testing Subprocess Restart Functionality")
    print("=" * 50)
    
    # Set up signal handler for clean exit
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start mock health monitor in background
    health_thread = threading.Thread(target=mock_health_monitor, daemon=True)
    health_thread.start()
    
    # Run mock data reader in main thread
    try:
        mock_data_reader()
        print("✅ Test completed successfully!")
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
