import time
import csv
import os
import subprocess
import threading
import queue
import re
import zmq
import traceback
from datetime import datetime
import serial
import json

# CONFIGURATION
SERIAL_PORT = '/dev/tty.usbserial-1410'  # Updated ESP32 USB port for macOS
BAUD_RATE = 115200
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# ZMQ communication for dosing controller
context = zmq.Context()
dosing_socket = context.socket(zmq.REP)
dosing_socket.bind("tcp://*:5555")

# Global variables
event_data = []
lock = threading.Lock()

# Event tracking variables
current_prgcal_count = 0
current_prgsample_count = 0
event_measurements = {}
current_event_type = None
current_event_num = None
current_action = None
current_cycle_num = None
event_processed_keys = set()
pending_ph_measurement = False
pending_ec_measurement = False

# CSV file variables
csv_file = None
csv_writer = None
event_csv_file = None
event_csv_writer = None

def send_command_to_esp32(command):
    """Send command to ESP32 via serial and return response"""
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2) as ser:
            ser.reset_input_buffer()
            
            if isinstance(command, dict):
                command_str = json.dumps(command) + '\n'
            else:
                command_str = str(command) + '\n'
            
            # Create simplified log for dosing commands
            if isinstance(command, dict) and command.get('action') == 'dose':
                pump_type = command.get('pump_type', 'unknown')
                pin = command.get('pin', 'unknown')
                duration_ms = command.get('duration_ms', '0')
                simplified_log = f"Dosing: {pump_type} on pin {pin} for {duration_ms}ms"
                print(simplified_log)
            else:
                print(f"Sending to ESP32: {command_str.strip()}")
            
            ser.write(command_str.encode())
            time.sleep(1)
            
            response = ""
            start_time = time.time()
            is_dosing = isinstance(command, dict) and command.get('action') == 'dose'
            dosing_complete = False
            
            while time.time() - start_time < 2:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        response += line + "\n"
                        
                        if is_dosing and "dosing_complete" in line:
                            dosing_complete = True
                        
                        if not is_dosing:
                            print(line)
                else:
                    if is_dosing and dosing_complete:
                        break
                    time.sleep(0.1)
            
            if is_dosing:
                if "success" in response and "dosing_complete" in response:
                    pass
                else:
                    print(f"Dosing failed: {pump_type} on pin {pin}")
                    
            return {"success": True, "response": response if response else "Command sent, no response"}
    except Exception as e:
        print(f"Serial communication error: {e}")
        return {"success": False, "error": str(e)}

def zmq_communication_thread():
    """Handle ZMQ communication with dosing controller"""
    while True:
        try:
            message = dosing_socket.recv_json()
            
            if message.get('action') == 'dose':
                pin = message.get('pin')
                duration_ms = message.get('duration_ms')
                pump_type = message.get('pump_type')
                
                simplified_log = f"Dosing: {pump_type} on pin {pin} for {duration_ms}ms"
                
                esp32_response = send_command_to_esp32(message)
                
                with lock:
                    event_data.append(simplified_log)
                
                # Write to current CSV file
                empty_sensor_data = [""] * 11
                csv_writer.writerow(empty_sensor_data + [simplified_log])
                csv_file.flush()

                # Record to event_data.csv
                dosing_match = re.search(r'Dosing: (.+?) on pin \d+ for (\d+)ms', simplified_log)
                if dosing_match:
                    dosing_action = dosing_match.group(1)
                    dosing_time_s = float(dosing_match.group(2)) / 1000.0
                    event_csv_writer.writerow([
                        current_cycle_num if current_cycle_num is not None else "",
                        "Dosing",
                        "",
                        dosing_action,
                        "",
                        dosing_time_s,
                        "", "", "", "", "", ""
                    ])
                    event_csv_file.flush()
                    print(f"✅ Recorded dosing event: {dosing_action}, dosing time: {dosing_time_s}s")
                
                dosing_socket.send_json(esp32_response)
            else:
                print(f"Received command: {message}")
                esp32_response = send_command_to_esp32(message)
                dosing_socket.send_json(esp32_response)
        
        except Exception as e:
            print(f"Error in ZMQ communication: {e}")
            try:
                dosing_socket.send_json({"success": False, "error": str(e)})
            except:
                pass
            time.sleep(1)

def process_event_line(line):
    """Process event line and extract relevant information"""
    global current_prgcal_count, current_prgsample_count, current_event_type, current_event_num, current_action, current_cycle_num
    global pending_ph_measurement, pending_ec_measurement
    
    # Detect cycles
    cycle_match = re.search(r'Starting new PRG(\w+) cycle \((\d+) of (\d+)\)', line)
    if cycle_match:
        event_type = f"PRG{cycle_match.group(1)}"
        cycle_num = int(cycle_match.group(2))
        
        if event_type == "PRGCal":
            current_prgcal_count = cycle_num
        elif event_type == "PRGSample":
            current_prgsample_count = cycle_num
            
        current_cycle_num = cycle_num
        print(f"🔄 Detected cycle: {event_type} #{cycle_num}")
        return None
    
    # pH and EC measurements
    if "PRGSample pH measurement" in line:
        if not pending_ph_measurement:
            current_action = "PRGSample pH measurement"
            pending_ph_measurement = True
            print("🧪 Detected PRGSample pH measurement – waiting for new sensor reading")
        return None
    
    if "PRGSample EC measurement" in line:
        if not pending_ec_measurement:
            current_action = "PRGSample EC measurement"
            pending_ec_measurement = True
            print("⚡ Detected PRGSample EC measurement – waiting for new sensor reading")
        return None
    
    if "PRGCal pH calibration point" in line:
        current_action = "pH calibration point"
        return None
    
    # Detect activated events
    event_match = re.search(r'PRG(\w+) Event #(\d+) activated', line)
    if event_match:
        event_type = f"PRG{event_match.group(1)}"
        event_num = int(event_match.group(2))
        current_event_type = event_type
        current_event_num = event_num
        return None
    
    return None

def read_data_from_platformio():
    """Read data from PlatformIO serial monitor"""
    global pending_ph_measurement, pending_ec_measurement, event_processed_keys
    global current_prgcal_count, current_prgsample_count, current_event_type, current_event_num, current_action, current_cycle_num
    
    try:
        print("Starting PlatformIO monitor subprocess...")
        process = subprocess.Popen(
            ['pio', 'device', 'monitor', '--port', SERIAL_PORT, '--baud', str(BAUD_RATE)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        
        while True:
            line = process.stdout.readline().decode('utf-8').strip()
            if line:
                process_event_line(line)
                
                # Detect pH/EC messages directly in lines
                if "PRGSample pH measurement" in line:
                    current_action = "PRGSample pH measurement"
                    pending_ph_measurement = True
                    print("🧪 Detected PRGSample pH measurement – waiting for new sensor reading")
                
                if "PRGSample EC measurement" in line:
                    current_action = "PRGSample EC measurement"
                    pending_ec_measurement = True
                    print("⚡ Detected PRGSample EC measurement – waiting for new sensor reading")
                
                # Process sensor data lines
                parts = line.split(',')
                if len(parts) >= 11:
                    try:
                        values = [float(part) for part in parts[:11]]
                        
                        # Write to time-based CSV
                        csv_writer.writerow(values + [""])
                        csv_file.flush()
                        
                        # Handle pending measurements
                        if pending_ph_measurement:
                            cycle_num = current_prgsample_count if current_prgsample_count else 1
                            event_action_key = f"PRGSample_pH_measurement_{cycle_num}"
                            if event_action_key not in event_processed_keys:
                                event_csv_writer.writerow([
                                    cycle_num, "PRGSample",
                                    current_event_num if current_event_num is not None else 5,
                                    "PRGSample pH measurement", values[0], "",
                                    values[4], values[5], values[6], values[7], values[8], values[9]
                                ])
                                event_csv_file.flush()
                                event_processed_keys.add(event_action_key)
                                print(f"✅ Recorded deferred pH measurement data for cycle {cycle_num}")
                            pending_ph_measurement = False
                        
                        if pending_ec_measurement:
                            cycle_num = current_prgsample_count if current_prgsample_count else 1
                            event_action_key = f"PRGSample_EC_measurement_{cycle_num}"
                            if event_action_key not in event_processed_keys:
                                event_csv_writer.writerow([
                                    cycle_num, "PRGSample",
                                    current_event_num if current_event_num is not None else 5,
                                    "PRGSample EC measurement", values[0], "",
                                    values[4], values[5], values[6], values[7], values[8], values[9]
                                ])
                                event_csv_file.flush()
                                event_processed_keys.add(event_action_key)
                                print(f"✅ Recorded deferred EC measurement data for cycle {cycle_num}")
                            pending_ec_measurement = False
                        
                        # Store event measurements
                        if current_event_type and current_event_num is not None:
                            event_key = f"{current_event_type}_{current_event_num}"
                            event_measurements[event_key] = [
                                values[0], values[4], values[5], values[6],
                                values[7], values[8], values[9]
                            ]
                        
                        # Record event data
                        if (current_event_type and current_event_num is not None and current_action is not None 
                            and current_action not in ["PRGSample pH measurement", "PRGSample EC measurement"]):
                            
                            cycle_num = None
                            if current_event_type == "PRGCal":
                                cycle_num = current_prgcal_count
                            elif current_event_type == "PRGSample":
                                cycle_num = current_prgsample_count
                            
                            event_action_key = f"{current_event_type}_{current_event_num}_{current_action}"
                            if event_action_key not in event_processed_keys:
                                event_csv_writer.writerow([
                                    cycle_num, current_event_type, current_event_num, current_action,
                                    values[0], "",
                                    values[4] if len(values) > 4 else 0.0,
                                    values[5] if len(values) > 5 else 0.0,
                                    values[6] if len(values) > 6 else 0.0,
                                    values[7] if len(values) > 7 else 0.0,
                                    values[8] if len(values) > 8 else 0.0,
                                    values[9] if len(values) > 9 else 0.0
                                ])
                                event_csv_file.flush()
                                event_processed_keys.add(event_action_key)
                                print(f"✅ Recorded event data for {current_event_type} #{current_event_num}, Cycle {cycle_num}, Action: {current_action}")
                                current_action = None
                        
                    except ValueError as ve:
                        print(f"Error converting data: {ve}")
                else:
                    # Log non-dosing events
                    if "Dosing:" in line:
                        dosing_match = re.search(r'Dosing:\s*(.+?)\s+for\s+(\d+)ms', line)
                        if dosing_match:
                            dosing_action = dosing_match.group(1)
                            dosing_time_s = float(dosing_match.group(2)) / 1000.0
                        else:
                            dosing_action = "Dosing"
                            dosing_time_s = ""
                        cycle_num = current_cycle_num if current_cycle_num is not None else ""
                        event_csv_writer.writerow([
                            cycle_num, "Dosing", "", dosing_action, "", dosing_time_s,
                            "", "", "", "", "", ""
                        ])
                        event_csv_file.flush()
                        print(f"✅ Recorded dosing event: {dosing_action}, dosing time: {dosing_time_s} s")
                    else:
                        # Log other events
                        should_log = True
                        dosing_patterns = [
                            '{"action":"dose"', '"action":"dosing_start"', '"action":"dosing_complete"',
                            'Activating pump on pin', 'Pump deactivated', 'Received command:'
                        ]
                        
                        for pattern in dosing_patterns:
                            if pattern in line:
                                should_log = False
                                break
                        
                        if should_log:
                            with lock:
                                event_data.append(line)
                            
                            # Write to CSV if not just empty sensor data
                            if line.strip() and not line.startswith('Time'):
                                empty_sensor_data = [""] * 11
                                csv_writer.writerow(empty_sensor_data + [line])
                                csv_file.flush()
                
    except Exception as e:
        print(f"Error in PlatformIO monitor: {e}")
        traceback.print_exc()

def start_data_collection_threads():
    """Start all data collection threads"""
    # Start ZMQ thread
    zmq_thread = threading.Thread(target=zmq_communication_thread)
    zmq_thread.daemon = True
    zmq_thread.start()
    print("Started ZMQ communication thread")
    
    # Start PlatformIO monitor thread
    monitor_thread = threading.Thread(target=read_data_from_platformio)
    monitor_thread.daemon = True
    monitor_thread.start()
    print("Started PlatformIO monitor thread")
    
    return zmq_thread, monitor_thread

def initialize_csv_files():
    """Initialize CSV files for data logging"""
    global csv_file, csv_writer, event_csv_file, event_csv_writer
    
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Sensor data CSV
    csv_filename = os.path.join(DATA_DIR, f'sensor_data_{current_time}.csv')
    csv_file = open(csv_filename, 'w', newline='')
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow([
        'Time (ms)', 'Photoresistor (V)', 'Abs (a.u.)', 'Conc (ppm)',
        'EC (V)', 'EC (mS/cm)', 'pH (V)', 'pH Value',
        'Nitrate (V)', 'Nitrate (ppm)', 'Temp(°C)', 'Event Info'
    ])
    
    # Event data CSV
    event_csv_filename = os.path.join(DATA_DIR, f'event_data_{current_time}.csv')
    event_csv_file = open(event_csv_filename, 'w', newline='')
    event_csv_writer = csv.writer(event_csv_file)
    event_csv_writer.writerow([
        'Cycle Number', 'Event Type', 'Event', 'Action', 'Time', 'Dosing Time (s)',
        'EC (V)', 'EC (ppm)', 'pH (V)', 'pH Value', 'Nitrate (V)', 'Nitrate (ppm)'
    ])
    
    print(f"CSV files initialized: {csv_filename}, {event_csv_filename}")

def main():
    """Main function to run data collection"""
    print("=== Hydroponic Data Collection System ===")
    print(f"Serial Port: {SERIAL_PORT}")
    print(f"Baud Rate: {BAUD_RATE}")
    print(f"Data Directory: {DATA_DIR}")
    print(f"ZMQ Server: tcp://*:5555")
    print("="*50)
    
    try:
        # Initialize CSV files
        initialize_csv_files()
        
        # Start data collection threads
        zmq_thread, monitor_thread = start_data_collection_threads()
        
        print("\n🚀 Data collection system started successfully!")
        print("📡 ESP32 serial communication active")
        print("🔄 ZMQ server listening for dosing controller")
        print("📝 CSV logging active")
        print("\n💡 Press Ctrl+C to stop...")
        
        # Keep main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Shutting down data collection system...")
    except Exception as e:
        print(f"❌ Error in main: {e}")
        traceback.print_exc()
    finally:
        # Close CSV files
        if csv_file:
            csv_file.close()
            print("📝 Sensor CSV file closed.")
        if event_csv_file:
            event_csv_file.close()
            print("📝 Event CSV file closed.")
        
        print("✅ Data collection system stopped.")

if __name__ == "__main__":
    main()
