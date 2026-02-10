#!/usr/bin/env python3
"""
Test script for PP1 (GPIO 14 / Channel 7) with user-defined duration - with dashboard logging
"""
import serial
import time
import sys
import zmq
import json

# Get duration from command line argument or prompt user
if len(sys.argv) > 1:
    try:
        duration_seconds = float(sys.argv[1])
    except ValueError:
        print("Invalid duration. Please enter a number in seconds.")
        sys.exit(1)
else:
    try:
        duration_seconds = float(input("Enter PP1 duration in seconds: "))
    except ValueError:
        print("Invalid input. Using default duration of 10 seconds.")
        duration_seconds = 10.0

# Convert to milliseconds for the ESP32
duration_ms = int(duration_seconds * 1000)

# Ensure only that duration is positive
if duration_seconds <= 0:
    print("Duration must be greater than 0. Using 0.5 seconds.")
    duration_seconds = 0.5
    duration_ms = 500

# Create the simplified log message
simplified_log = f"Activation: PP1 on GPIO 14 (Channel 7) for {duration_ms}ms"
print(simplified_log)

try:
    # First notify the dashboard via ZMQ
    try:
        # Set up ZMQ connection to dashboard
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect("tcp://localhost:5555")
        socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1 second timeout
        
        # Create command similar to what dosing controller would send
        command = {
            "action": "activate",
            "pin": 14,
            "duration_ms": duration_ms,
            "channel": 7,
            "device_type": "PP1",
            "log_message": simplified_log
        }
        
        # Send to dashboard
        socket.send_json(command)
        print("Sent command to dashboard")
        
        # Get response (with timeout)
        try:
            response = socket.recv_json()
            print("Dashboard acknowledged")
        except zmq.error.Again:
            print("Dashboard did not respond (timeout)")
        
    except Exception as e:
        print(f"Failed to notify dashboard: {e}")

    # Now communicate with ESP32 directly as before
    # with serial.Serial("/dev/cu.usbserial-13120", 115200, timeout=1) as ser:
        # Clear any pending data
        # ser.reset_input_buffer()
        
        # Send JSON command for PP1 channel activation with user-defined duration
        # cmd = f'{{"action":"activate","pin":14,"duration_ms":{duration_ms},"channel":7,"device_type":"PP1"}}\n'.encode()
        # ser.write(cmd)
        
        # Track activation events without showing raw responses
        # start_time = time.time()
        # activation_started = False
        # activation_complete = False
        
        # Monitor for duration + 5 seconds but filter responses
        # monitor_time = duration_seconds + 5
        # while time.time() - start_time < monitor_time:
            # if ser.in_waiting:
                # response = ser.readline().decode().strip()
                
                # Track status without printing raw responses
                # if "activation_start" in response and not activation_started:
                    # activation_started = True
                    # print("PP1 activated")
                
                # if "activation_complete" in response and not activation_complete:
                    # activation_complete = True
                    # print("PP1 deactivated")
                
            # time.sleep(0.1)
        
        # if not activation_complete:
            # print("Warning: Activation may not have completed properly")

    # Simular o tempo que o PP1 estaria a funcionar
    print(f"Simulating PP1 activation for {duration_seconds:.1f} seconds...")
    time.sleep(duration_seconds)
    print("Simulated PP1 activation complete.")

# except serial.SerialException as e:
    # print(f"Error: Could not open serial port: {e}")
except KeyboardInterrupt:
    print("\nTest interrupted by user.")
    # Try to send stop command if interrupted
    # try:
        # if 'ser' in locals() and ser.is_open:
            # ser.write(b'{"action":"stop","pin":14}\n')
            # print("Sent stop command to PP1.")
    # except:
        # pass
