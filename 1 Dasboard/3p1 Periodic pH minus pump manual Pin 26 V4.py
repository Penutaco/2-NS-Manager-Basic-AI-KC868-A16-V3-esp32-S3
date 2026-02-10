#!/usr/bin/env python3
"""
Test script for pH minus pump on pin 26 with user-defined duration and periodicity - with dashboard logging
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
        print("Invalid duration. Please enter a number in seconds for the first argument.")
        sys.exit(1)
else:
    try:
        duration_seconds = float(input("Enter pump activation duration in seconds: "))
    except ValueError:
        print("Invalid input. Using default activation duration of 10 seconds.")
        duration_seconds = 10.0

# Convert to milliseconds for the ESP32
duration_ms = int(duration_seconds * 1000)

# Ensure only that duration is positive
if duration_seconds <= 0:
    print("Duration must be greater than 0. Using 0.5 seconds.")
    duration_seconds = 0.5
    duration_ms = 500

# --- Get Pump Periodicity ---
if len(sys.argv) > 2:
    try:
        periodicity_minutes = float(sys.argv[2])
    except ValueError:
        print("Invalid periodicity. Please enter a number in minutes for the second argument.")
        sys.exit(1)
else:
    try:
        periodicity_minutes = float(input(f"Enter pump periodicity in minutes (how often to run for {duration_seconds}s): "))
    except ValueError:
        print("Invalid input. Using default periodicity of 60 minutes.")
        periodicity_minutes = 60.0

# Ensure periodicity is positive
if periodicity_minutes <= 0:
    print("Periodicity must be greater than 0. Using default periodicity of 60 minutes.")
    periodicity_minutes = 60.0

periodicity_seconds = int(periodicity_minutes * 60)

print(f"Configuration: Pump will activate for {duration_seconds:.1f} seconds every {periodicity_minutes:.1f} minutes.")
print("Press Ctrl+C to stop.")


try:
    while True: # <<< START OF THE PERIODIC LOOP
        # Create the simplified log message
        simplified_log = f"Dosing: ph_minus on pin 26 for {duration_ms}ms (Periodic)"
        print(f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} - {simplified_log}") # Moved print here

        # First notify the dashboard via ZMQ
        try:
            # Set up ZMQ connection to dashboard
            context = zmq.Context()
            socket = context.socket(zmq.REQ)
            socket.connect("tcp://localhost:5555")
            socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1 second timeout
            
            # Create command similar to what dosing controller would send
            command = {
                "action": "dose",
                "pin": 26,
                "duration_ms": duration_ms,
                "pump_type": "ph_minus",
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

        # Now communicate with ESP32 directly as before (THIS PART REMAINS COMMENTED AS PER ORIGINAL)
        # with serial.Serial("/dev/cu.usbserial-110", 115200, timeout=1) as ser:
            # Clear any pending data
            # ser.reset_input_buffer()
            
            # Send JSON command for pH minus pump with user-defined duration
            # cmd = f'{{"action":"dose","pin":26,"duration_ms":{duration_ms},"pump_type":"ph_minus"}}\n'.encode()
            # ser.write(cmd)
            
            # Track dosing events without showing raw responses
            # start_time = time.time()
            # dosing_started = False
            # dosing_complete = False
            
            # Monitor for duration + 5 seconds but filter responses
            # monitor_time = duration_seconds + 5
            # while time.time() - start_time < monitor_time:
                # if ser.in_waiting:
                    # response = ser.readline().decode().strip()
                    
                    # Track status without printing raw responses
                    # if "dosing_start" in response and not dosing_started:
                        # dosing_started = True
                        # print("Pump activated")
                    
                    # if "dosing_complete" in response and not dosing_complete:
                        # dosing_complete = True
                        # print("Pump deactivated")
                    
                # time.sleep(0.1)
            
            # if not dosing_complete:
                # print("Warning: Dosing may not have completed properly")

        # Simular o tempo que a bomba estaria a funcionar
        print(f"Simulating pump action for {duration_seconds:.1f} seconds...")
        time.sleep(duration_seconds)
        print("Simulated pump action complete.")

        # Wait for the next period
        print(f"Waiting for {periodicity_minutes:.1f} minutes ({periodicity_seconds} seconds) until next activation...")
        time.sleep(periodicity_seconds)
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Period ended. Preparing for next activation.")

# except serial.SerialException as e: # This is commented as the serial part is commented
    # print(f"Error: Could not open serial port: {e}")
except KeyboardInterrupt:
    print("\nProgram interrupted by user.") # Changed message slightly for clarity
    # Try to send stop command if interrupted (THIS PART REMAINS COMMENTED AS PER ORIGINAL)
    # try:
        # if 'ser' in locals() and ser.is_open:
            # ser.write(b'{"action":"stop","pin":26}\n')
            # print("Sent stop command to pump.")
    # except:
        # pass