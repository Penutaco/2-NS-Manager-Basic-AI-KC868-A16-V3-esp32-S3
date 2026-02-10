import time
import csv
import os
import subprocess
import threading
import queue
import copy
import re
import zmq
import time
import traceback
import glob
from collections import deque
from datetime import datetime, timedelta
from dash import dcc, html
from dash.dependencies import Output, Input
import dash
import plotly.graph_objs as go
import sys
import dash_bootstrap_components as dbc
import serial
import json

# CONFIGURATION
SERIAL_PORT = '/dev/cu.usbmodem1301'  # ESP32-S3 USB CDC port
BAUD_RATE = 115200
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# HEALTH MONITORING CONFIGURATION
HEALTH_CHECK_INTERVAL = 30  # Check every 30 seconds
CONNECTION_TIMEOUT = 60     # Consider connection lost after 60 seconds
RECONNECTION_ATTEMPTS = 3   # Number of reconnection attempts before port scan
PORT_SCAN_PATTERN = '/dev/cu.usbserial*'  # Pattern for macOS USB serial ports to scan

# Health monitoring global variables
last_data_received = None
connection_healthy = False
current_serial_port = SERIAL_PORT
health_monitor_active = True
connection_status_log = []
reconnection_in_progress = False

# Smart port cycling variables
detected_ports = []  # List of actually detected ESP32 ports
current_port_index = 0  # Index of current port in detected_ports list
last_port_scan_time = 0  # Timestamp of last port scan

# Subprocess restart coordination
restart_subprocess_flag = threading.Event()
current_process = None  # Store the subprocess reference

# ZMQ communication for dosing controller
context = zmq.Context()
dosing_socket = context.socket(zmq.REP)
dosing_socket.bind("tcp://*:5555")

# HEALTH MONITORING FUNCTIONS
def log_connection_status(message, level="INFO"):
    """Log connection status messages with timestamps"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    status_entry = f"[{timestamp}] {level}: {message}"
    connection_status_log.append(status_entry)
    
    # Keep only last 1000 entries
    if len(connection_status_log) > 1000:
        connection_status_log.pop(0)
    
    # Print with appropriate emoji
    emoji_map = {
        "INFO": "ℹ️",
        "SUCCESS": "✅", 
        "WARNING": "⚠️",
        "ERROR": "❌",
        "RECOVERY": "🔍"
    }
    print(f"{emoji_map.get(level, 'ℹ️')} {status_entry}")
    
    # Write health status for important events
    if level in ["ERROR", "SUCCESS", "WARNING"]:
        try:
            write_health_status()
        except:
            pass  # Don't let health status writing break the main logging

def scan_all_esp32_ports():
    """Scan and return ALL available USB ports that have ESP32"""
    global detected_ports, last_port_scan_time
    
    try:
        available_ports = glob.glob(PORT_SCAN_PATTERN)
        available_ports.sort()  # Sort for consistent ordering
        
        log_connection_status(f"Scanning USB ports: {available_ports}", "RECOVERY")
        
        # Test all ports and collect working ones
        working_ports = []
        for port in available_ports:
            if test_port_connection(port):
                working_ports.append(port)
        
        # Update global detected ports list
        detected_ports = working_ports
        last_port_scan_time = time.time()
        
        log_connection_status(f"Detected ESP32 ports: {detected_ports}", "RECOVERY")
        return detected_ports
        
    except Exception as e:
        log_connection_status(f"Error scanning all ports: {e}", "ERROR")
        return []

def get_next_port_to_try():
    """Get the next port to try from the detected ports list, cycling through them"""
    global current_port_index, detected_ports, current_serial_port
    
    # If no detected ports, scan first
    if not detected_ports or time.time() - last_port_scan_time > 60:  # Re-scan every 60 seconds
        scan_all_esp32_ports()
    
    # If still no ports detected, return None
    if not detected_ports:
        return None
    
    # Find current port index, or start from 0
    try:
        current_port_index = detected_ports.index(current_serial_port)
    except ValueError:
        current_port_index = 0
    
    # Try next port in the list (cycling)
    current_port_index = (current_port_index + 1) % len(detected_ports)
    next_port = detected_ports[current_port_index]
    
    log_connection_status(f"Smart port cycling: trying {next_port} (index {current_port_index}/{len(detected_ports)-1})", "RECOVERY")
    return next_port

def scan_for_esp32_ports():
    """Legacy function - now uses smart port cycling"""
    return get_next_port_to_try()

def test_port_connection(port, timeout=3):
    """Test if a specific port has the ESP32 responding"""
    try:
        log_connection_status(f"Testing connection to {port}", "RECOVERY")
        # Increase timeout to 10 seconds
        timeout = 10
        with serial.Serial(port, BAUD_RATE, timeout=timeout) as ser:
            ser.reset_input_buffer()
            time.sleep(3)  # Increased to 3 seconds for initial data
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

def attempt_reconnection():
    global current_serial_port, connection_healthy, reconnection_in_progress
    
    if reconnection_in_progress:
        return False
    
    reconnection_in_progress = True
    log_connection_status("Starting connection recovery process with smart port cycling", "RECOVERY")
    
    # Maximum number of full port cycles before giving up
    max_cycles = 500
    cycle_count = 0
    
    # Don't try the current failing port first - go straight to port cycling
    while cycle_count < max_cycles:
        # Get the next port to try from detected ports (cycles through available ports)
        log_connection_status("Smart cycling to next available ESP32 port", "RECOVERY")
        new_port = get_next_port_to_try()
        
        if new_port and new_port != current_serial_port:
            # Try the new port
            old_port = current_serial_port
            current_serial_port = new_port
            log_connection_status(f"Switching from {old_port} to {current_serial_port}", "RECOVERY")
            
            if test_port_connection(current_serial_port):
                restart_subprocess_flag.set()
                log_connection_status("Signaling subprocess restart for new port", "RECOVERY")
                time.sleep(3)
                
                test_response = send_command_to_esp32("ping")
                if test_response.get("success"):
                    # Wait for new data to be received
                    wait_start = time.time()
                    last_seen = last_data_received
                    data_timeout = 20  # seconds
                    while time.time() - wait_start < data_timeout:
                        if last_data_received != last_seen:
                            connection_healthy = True
                            log_connection_status(f"Sensor data received after port switch to {current_serial_port}", "SUCCESS")
                            reconnection_in_progress = False
                            return True
                        time.sleep(0.5)
                    connection_healthy = False
                    log_connection_status(f"No sensor data received after port switch to {current_serial_port} (waited {data_timeout}s)", "ERROR")
                else:
                    connection_healthy = False
                    log_connection_status(f"Direct serial test FAILED on {current_serial_port}: {test_response.get('error', 'No response')}", "ERROR")
            else:
                log_connection_status(f"Port connection test failed for {current_serial_port}", "ERROR")
        
        elif new_port == current_serial_port:
            # All ports tried, back to current - try it once more
            log_connection_status(f"Cycled through all ports, testing current port {current_serial_port} again", "RECOVERY")
            if test_port_connection(current_serial_port):
                restart_subprocess_flag.set()
                log_connection_status("Signaling subprocess restart after successful reconnection", "RECOVERY")
                time.sleep(3)
                
                test_response = send_command_to_esp32("ping")
                if test_response.get("success"):
                    wait_start = time.time()
                    last_seen = last_data_received
                    data_timeout = 20
                    while time.time() - wait_start < data_timeout:
                        if last_data_received != last_seen:
                            connection_healthy = True
                            log_connection_status(f"Sensor data received after reconnection on {current_serial_port}", "SUCCESS")
                            reconnection_in_progress = False
                            return True
                        time.sleep(0.5)
                    connection_healthy = False
                    log_connection_status(f"No sensor data received after reconnection on {current_serial_port} (waited {data_timeout}s)", "ERROR")
                else:
                    connection_healthy = False
                    log_connection_status(f"Direct serial test after reconnection FAILED on {current_serial_port}: {test_response.get('error', 'No response')}", "ERROR")
        else:
            # No ports detected at all
            log_connection_status("No ESP32 ports detected, rescanning in 10 seconds...", "WARNING")
            time.sleep(10)
            # Force a rescan
            scan_all_esp32_ports()
        
        # Increment cycle counter and wait before trying next port in cycle
        cycle_count += 1
        time.sleep(5)
    
    # Exit after maximum cycles reached
    log_connection_status(f"Connection recovery failed after {max_cycles} cycles", "ERROR")
    reconnection_in_progress = False
    return False

def update_data_timestamp():
    """Update the last data received timestamp"""
    global last_data_received
    last_data_received = datetime.now()
    # Update health status file whenever we receive data
    write_health_status()

def write_health_status():
    """Write current health status to JSON file for watchdog monitoring"""
    try:
        health_data = {
            'last_update': datetime.now().isoformat(),
            'connection_healthy': connection_healthy,
            'last_data_received': last_data_received.isoformat() if last_data_received else None,
            'current_port': current_serial_port,
            'reconnection_in_progress': reconnection_in_progress,
            'health_monitor_active': health_monitor_active,
            'recent_errors': connection_status_log[-5:] if connection_status_log else []  # Last 5 log entries
        }
        
        health_file_path = os.path.join(DATA_DIR, 'dashboard_health.json')
        with open(health_file_path, 'w') as f:
            json.dump(health_data, f, indent=2)
            
    except Exception as e:
        # Don't log this error to avoid spam, just print it
        print(f"Warning: Could not write health status file: {e}")

def health_monitor_thread():
    global connection_healthy, health_monitor_active, last_data_received
    
    log_connection_status("Health monitor started", "SUCCESS")
    
    # Add: Initial wait for first data
    initial_wait_start = time.time()
    initial_data_timeout = 15  # seconds (adjust as needed)
    while health_monitor_active and last_data_received is None:
        if time.time() - initial_wait_start > initial_data_timeout:
            log_connection_status(f"No data received after {initial_data_timeout}s on startup, triggering reconnection", "ERROR")
            attempt_reconnection()
            # Reset timer after reconnection attempt
            initial_wait_start = time.time()
        time.sleep(1)
    
    while health_monitor_active:
        try:
            time.sleep(HEALTH_CHECK_INTERVAL)
            
            # Write health status every cycle
            write_health_status()
            
            if last_data_received is None:
                # No data received yet, skip this check (handled by initial wait above)
                continue
            
            # Calculate time since last data
            time_since_data = (datetime.now() - last_data_received).total_seconds()
            
            if time_since_data > CONNECTION_TIMEOUT:
                if connection_healthy:
                    connection_healthy = False
                    log_connection_status(f"Connection lost - no data for {time_since_data:.0f} seconds", "ERROR")
                    write_health_status()  # Update status after change
                    
                    # Attempt automatic recovery
                    if attempt_reconnection():
                        log_connection_status("Automatic recovery successful", "SUCCESS")
                        write_health_status()  # Update status after recovery
                    else:
                        log_connection_status("Automatic recovery failed - manual intervention may be required", "ERROR")
                        write_health_status()  # Update status after failure
            else:
                if not connection_healthy:
                    connection_healthy = True
                    log_connection_status("Connection restored", "SUCCESS")
                    write_health_status()  # Update status after change
                    
        except Exception as e:
            log_connection_status(f"Health monitor error: {e}", "ERROR")
            time.sleep(5)  # Wait a bit before retrying

# Function to send command to ESP32 via serial
def send_command_to_esp32(command):
    """Envia comando para o ESP32 via serial e retorna a resposta"""
    global current_serial_port
    
    try:
        # Abrir conexão serial usando porta dinâmica
        with serial.Serial(current_serial_port, BAUD_RATE, timeout=2) as ser:
            # Limpar buffer
            ser.reset_input_buffer()
            
            # Adicionar nova linha ao final do comando
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
                print(simplified_log)  # Print simplified log instead of raw command
            else:
                print(f"Sending to ESP32: {command_str.strip()}")
            
            # Enviar comando
            ser.write(command_str.encode())
            
            # Aguardar e ler resposta
            time.sleep(1)  # Dar tempo para o ESP32 processar
            
            response = ""
            start_time = time.time()
            
            # For dosing commands, we'll collect responses but not print them individually
            is_dosing = isinstance(command, dict) and command.get('action') == 'dose'
            dosing_complete = False
            
            # Ler até timeout ou não ter mais dados
            while time.time() - start_time < 2:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        # Add to response but don't print raw responses for dosing commands
                        response += line + "\n"
                        
                        # Track if dosing completed successfully
                        if is_dosing and "dosing_complete" in line:
                            dosing_complete = True
                        
                        # Only print non-dosing responses
                        if not is_dosing:
                            print(line)
                else:
                    # No more data to read
                    if is_dosing and dosing_complete:
                        # Don't wait full timeout if dosing is complete
                        break
                    time.sleep(0.1)
            
            # For dosing, print simple completion message
            if is_dosing:
                if "success" in response and "dosing_complete" in response:
                    pass  # We already printed the simplified log
                else:
                    print(f"Dosing failed: {pump_type} on pin {pin}")
                    
            return {"success": True, "response": response if response else "Command sent, no response"}
    except Exception as e:
        print(f"Serial communication error: {e}")
        return {"success": False, "error": str(e)}

# Start ZMQ communication thread
def zmq_communication_thread():
    while True:
        try:
            # Wait for message from dosing controller
            message = dosing_socket.recv_json()
            
            # For dosing commands, use simplified format
            if message.get('action') == 'dose':
                pin = message.get('pin')
                duration_ms = message.get('duration_ms')
                pump_type = message.get('pump_type')
                
                # Use simplified log format
                simplified_log = f"Dosing: {pump_type} on pin {pin} for {duration_ms}ms"
                
                # Process dosing command but don't print raw data
                esp32_response = send_command_to_esp32(message)
                
                # Add only the simplified log to event data
                with lock:
                    event_data.append(simplified_log)
                
                # Append to current CSV file with simplified format
                empty_sensor_data = [""] * 11
                csv_writer.writerow(empty_sensor_data + [simplified_log])
                csv_file.flush()

                # Também registrar no event_data.csv
                dosing_match = re.search(r'Dosing: (.+?) on pin \d+ for (\d+)ms', simplified_log)
                if dosing_match:
                    dosing_action = dosing_match.group(1)
                    dosing_time_s = float(dosing_match.group(2)) / 1000.0
                    event_csv_writer.writerow([
                        current_cycle_num if current_cycle_num is not None else "",  # Cycle Number
                        "Dosing",          # Event Type
                        "",                # Event (não aplicável)
                        dosing_action,     # Action: descrição da dosagem
                        "",                # Time: sem timestamp de sensor
                        dosing_time_s,     # Dosing Time (s)
                        "", "", "", "", "", ""
                    ])
                    event_csv_file.flush()
                    print(f"✅ Recorded dosing event: {dosing_action}, dosing time: {dosing_time_s}s")
                
                # Send response back to dosing controller
                dosing_socket.send_json(esp32_response)
            else:
                # Non-dosing commands use original handling
                print(f"Received command: {message}")
                esp32_response = send_command_to_esp32(message)
                dosing_socket.send_json(esp32_response)
        
        except Exception as e:
            print(f"Error in ZMQ communication: {e}")
            # Send error response
            try:
                dosing_socket.send_json({"success": False, "error": str(e)})
            except:
                pass
            time.sleep(1)  # Avoid tight loop on error

data_queue = queue.Queue()
csv_file = None

# Global data storage - Rolling window for 12 hours of data
# Assuming ~1 data point per second, 12 hours = 43,200 points
# Using 50,000 as safe maximum for deque
MAX_DATA_POINTS_12H = 50000
global_data = deque(maxlen=MAX_DATA_POINTS_12H)
event_data = []

# New tracking for PRGCal and PRGSample events
current_prgcal_count = 0
current_prgsample_count = 0
event_measurements = {}  # Store measurements for each event cycle
current_event_type = None  # Track current event type (PRGCal or PRGSample)
current_event_num = None   # Track current event number
current_action = None      # Track current action (e.g., pH measurement)
current_cycle_num = None   # Track current cycle number
event_processed_keys = set()  # Track processed event-action combinations

# Adicionar variáveis para adiar a gravação dos eventos
pending_ph_measurement = False
pending_ec_measurement = False

lock = threading.Lock()

# Create CSV files
current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
csv_filename = os.path.join(DATA_DIR, f'sensor_data_{current_time}.csv')
csv_file = open(csv_filename, 'w', newline='')
csv_writer = csv.writer(csv_file)

# Event CSV for structured data
event_csv_filename = os.path.join(DATA_DIR, f'event_data_{current_time}.csv')
event_csv_file = open(event_csv_filename, 'w', newline='')
event_csv_writer = csv.writer(event_csv_file)

# Update the CSV header with new column names
csv_writer.writerow([
    'Time (ms)', 'Photoresistor (V)', 'Abs (a.u.)', 'Conc (ppm)',
    'EC (V)', 'EC (mS/cm)', 'pH (V)', 'pH Value',
    'Nitrate (V)', 'Nitrate (ppm)', 'Temp(°C)', 'Event Info'
])

# Initialize event CSV with base headers
event_csv_writer.writerow([
    'Cycle Number',
    'Event Type',
    'Event',
    'Action',
    'Time',
    'Dosing Time (s)',
    'EC (V)',
    'EC (ppm)',
    'pH (V)',
    'pH Value',
    'Nitrate (V)',
    'Nitrate (ppm)'
])

# Create extracted_cycle_data CSV with additional columns for dosing
extracted_filename = os.path.join(DATA_DIR, f'extracted_cycle_data_{current_time}.csv')
with open(extracted_filename, 'w', newline='') as f:
    writer = csv.writer(f)
    # Copy the same header from event CSV and add dosing columns
    writer.writerow([
        'Event Type', 'Cycle Number', 'Time',
        'EC (V)', 'EC (mS/cm)', 'pH (V)', 'pH Value', 
        'Nitrate (V)', 'Nitrate (ppm)'
    ])

# Modificar a função process_event_line para capturar corretamente ciclos
def process_event_line(line):
    """Processa a linha de evento e extrai informações relevantes"""
    global current_prgcal_count, current_prgsample_count, current_event_type, current_event_num, current_action, current_cycle_num
    global pending_ph_measurement, pending_ec_measurement
    
    # Detectar ciclos - melhorar o regex para capturar "Starting new PRGSample cycle (N of M)"
    cycle_match = re.search(r'Starting new PRG(\w+) cycle \((\d+) of (\d+)\)', line)
    if cycle_match:
        event_type = f"PRG{cycle_match.group(1)}"
        cycle_num = int(cycle_match.group(2))
        
        # Atualizar o contador específico do ciclo
        if event_type == "PRGCal":
            current_prgcal_count = cycle_num
        elif event_type == "PRGSample":
            current_prgsample_count = cycle_num
            
        # Atualizar o ciclo global para refletir o ciclo atual
        current_cycle_num = cycle_num
        print(f"🔄 Detected cycle: {event_type} #{cycle_num}")
        
        return None
    
    # Associar pH measurement ao evento PRGSample
    if "PRGSample pH measurement" in line:
        if not pending_ph_measurement:
            current_action = "PRGSample pH measurement"
            pending_ph_measurement = True
            print("🧪 Detected PRGSample pH measurement – aguardando nova leitura de sensor")
        return None
    
    # Associar EC measurement ao evento PRGSample
    if "PRGSample EC measurement" in line:
        if not pending_ec_measurement:
            current_action = "PRGSample EC measurement"
            pending_ec_measurement = True
            print("⚡ Detected PRGSample EC measurement – aguardando nova leitura de sensor")
        return None
    
    if "PRGCal pH calibration point" in line:
        current_action = "pH calibration point"
        return None
    
    # Detectar eventos ativados
    event_match = re.search(r'PRG(\w+) Event #(\d+) activated', line)
    if event_match:
        event_type = f"PRG{event_match.group(1)}"
        event_num = int(event_match.group(2))
        current_event_type = event_type
        current_event_num = event_num
        return None
    
    return None

def read_data_from_platformio():
    global pending_ph_measurement, pending_ec_measurement, event_processed_keys
    global current_prgcal_count, current_prgsample_count, current_event_type, current_event_num, current_action, current_cycle_num
    global current_process, restart_subprocess_flag
    
    # Enhanced format data storage
    enhanced_data = {
        'sensor': deque(maxlen=MAX_DATA_POINTS_12H),
        'events': deque(maxlen=1000),
        'status': deque(maxlen=1000),
        'dosing_calc': deque(maxlen=1000),
        'dosing_action': deque(maxlen=1000),
        'learning': deque(maxlen=1000)
    }
    
    # Counter for filtered spam messages
    filtered_messages_count = 0
    
    def parse_enhanced_format(line):
        """Parse enhanced serial format lines"""
        if not line.startswith(('SENSOR,', 'EVENT,', 'STATUS,', 'DOSING_CALC,', 'CONVERSION,', 'COEFFICIENT,', 'LEARNING,')):
            return None
            
        parts = line.split(',')
        format_type = parts[0]
        
        try:
            if format_type == 'SENSOR':
                # SENSOR,timestamp,cycle_id,event_num,photo_volt,absorbance,concentration,ec_volt,ec_mscm,ph_volt,ph_value,nitrate_volt,temperature,stage,event_id
                if len(parts) >= 15:
                    data = {
                        'type': 'SENSOR',
                        'timestamp': int(parts[1]),
                        'cycle_id': int(parts[2]),
                        'event_num': int(parts[3]),
                        'photo_volt': float(parts[4]),
                        'absorbance': float(parts[5]),
                        'concentration': float(parts[6]),
                        'ec_volt': float(parts[7]),
                        'ec_mscm': float(parts[8]),
                        'ph_volt': float(parts[9]),
                        'ph_value': float(parts[10]),
                        'nitrate_volt': float(parts[11]),
                        'temperature': float(parts[12]),
                        'stage': int(parts[13]),
                        'event_id': parts[14]
                    }
                    return data
                    
            elif format_type == 'EVENT':
                # EVENT,timestamp,cycle_id,event_type,event_number,action,ph_measurement,ec_measurement,processing_time_ms,file_position
                if len(parts) >= 10:
                    data = {
                        'type': 'EVENT',
                        'timestamp': int(parts[1]),
                        'cycle_id': int(parts[2]),
                        'event_type': parts[3],
                        'event_number': int(parts[4]),
                        'action': parts[5],
                        'ph_measurement': float(parts[6]),
                        'ec_measurement': float(parts[7]),
                        'processing_time_ms': int(parts[8]),
                        'file_position': int(parts[9])
                    }
                    return data
                    
            elif format_type == 'STATUS':
                # STATUS,timestamp,cycle_id,stage,ph_within_tolerance,ec_within_tolerance,last_dosing_time,cycles_since_dosing,system_health,error_count
                if len(parts) >= 10:
                    data = {
                        'type': 'STATUS',
                        'timestamp': int(parts[1]),
                        'cycle_id': int(parts[2]),
                        'stage': int(parts[3]),
                        'ph_within_tolerance': parts[4] == 'true',
                        'ec_within_tolerance': parts[5] == 'true',
                        'last_dosing_time': int(parts[6]),
                        'cycles_since_dosing': int(parts[7]),
                        'system_health': int(parts[8]),
                        'error_count': int(parts[9])
                    }
                    return data
                    
            elif format_type == 'DOSING_CALC':
                # DOSING_CALC,timestamp,cycle_id,target_ph,current_ph,ph_diff,target_ec,current_ec,ec_diff,titration_coeff,calculated_volume,adjusted_volume,dosing_time_ms,pump_type,pin_number,stage,safety_factor,dosing_count,division_factor
                if len(parts) >= 19:
                    data = {
                        'type': 'DOSING_CALC',
                        'timestamp': int(parts[1]),
                        'cycle_id': int(parts[2]),
                        'target_ph': float(parts[3]),
                        'current_ph': float(parts[4]),
                        'ph_diff': float(parts[5]),
                        'target_ec': float(parts[6]),
                        'current_ec': float(parts[7]),
                        'ec_diff': float(parts[8]),
                        'titration_coeff': float(parts[9]),
                        'calculated_volume': float(parts[10]),
                        'adjusted_volume': float(parts[11]),
                        'dosing_time_ms': int(parts[12]),
                        'pump_type': parts[13],
                        'pin_number': int(parts[14]),
                        'stage': int(parts[15]),
                        'safety_factor': float(parts[16]),
                        'dosing_count': int(parts[17]),
                        'division_factor': int(parts[18])
                    }
                    return data
                    
        except (ValueError, IndexError) as e:
            print(f"Error parsing enhanced format line: {line[:100]}... Error: {e}")
            return None
            
        return None
    
    try:
        print("Starting PlatformIO monitor subprocess...")
        print("Supporting both legacy and enhanced serial formats...")
        print("🔇 Message filtering active: Continuous calculation spam will be filtered out")
        
        # Use current_serial_port for health monitoring
        global current_serial_port
        log_connection_status(f"Starting monitoring on {current_serial_port}", "INFO")
        
        current_process = subprocess.Popen(
            ['/Library/Frameworks/Python.framework/Versions/3.13/bin/pio', 'device', 'monitor', '--port', current_serial_port, '--baud', str(BAUD_RATE)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        
        last_sensor_values = None
        
        while True:
            # Check if restart was requested
            if restart_subprocess_flag.is_set():
                log_connection_status(f"Restarting subprocess with new port: {current_serial_port}", "RECOVERY")
                
                # Close current process
                if current_process:
                    try:
                        current_process.terminate()
                        current_process.wait(timeout=5)  # Wait up to 5 seconds for clean shutdown
                    except subprocess.TimeoutExpired:
                        log_connection_status("Process termination timeout, killing forcefully", "WARNING")
                        current_process.kill()
                        current_process.wait()
                    except Exception as e:
                        log_connection_status(f"Error terminating process: {e}", "WARNING")
                
                # Start new process with updated port
                try:
                    current_process = subprocess.Popen(
                        ['/Library/Frameworks/Python.framework/Versions/3.13/bin/pio', 'device', 'monitor', '--port', current_serial_port, '--baud', str(BAUD_RATE)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    
                    # Clear the restart flag
                    restart_subprocess_flag.clear()
                    log_connection_status(f"Subprocess restarted successfully on {current_serial_port}", "SUCCESS")
                    
                except Exception as e:
                    log_connection_status(f"Failed to restart subprocess: {e}", "ERROR")
                    restart_subprocess_flag.clear()  # Clear flag even on failure to avoid infinite loop
                    time.sleep(5)  # Wait before trying again
                    continue
            
            # Continue with normal data reading
            line = current_process.stdout.readline().decode('utf-8').strip()
            if line:
                # Skip header lines
                if "Enhanced Serial Format" in line or "Formats:" in line or "Legacy format:" in line or "Starting Enhanced" in line:
                    print(f"ESP32: {line}")
                    continue
                
                # Filter out continuous dosing calculation spam messages
                calculation_spam_patterns = [
                    'DEPRECATED_FUNCTION_WARNING',
                    'DOSE_CALC_PH_LEGACY',
                    'VOLUME_TO_TIME',
                    'DOSING_CALC,',
                    'calculateDosingVolume',
                    'dosingCalculation',
                    'calculatepHDose',
                    'Legacy dosing',
                    'Calculating volume',
                    'pH difference:'
                ]
                
                # Important events to preserve (never filter these out)
                important_events = [
                    'COEFFICIENT_UPDATE',
                    'PRGSample',
                    'PRGCal',
                    'Dosing:',  # Actual dosing actions
                    'Event #',  # Event activation messages
                    'completed',  # Event completion messages
                    'activated',  # Event activation
                    'measurement'  # Measurement events
                ]
                
                # Check if line contains important events first
                is_important_event = False
                for important_pattern in important_events:
                    if important_pattern in line:
                        is_important_event = True
                        break
                
                # If it's not an important event, check for calculation spam
                should_skip_line = False
                if not is_important_event:
                    for pattern in calculation_spam_patterns:
                        if pattern in line:
                            should_skip_line = True
                            break
                
                # Skip the line if it's identified as calculation spam
                if should_skip_line:
                    filtered_messages_count += 1
                    # Report periodically to show filtering is working
                    if filtered_messages_count % 50 == 0:
                        print(f"🔇 Filtered {filtered_messages_count} calculation spam messages")
                    continue
                
                # Try to parse enhanced format first
                enhanced_data_point = parse_enhanced_format(line)
                if enhanced_data_point:
                    # Handle enhanced format data
                    data_type = enhanced_data_point['type']
                    
                    if data_type == 'SENSOR':
                        # Convert to legacy format for compatibility with existing dashboard
                        legacy_values = [
                            enhanced_data_point['timestamp'] / 1000.0,  # Convert to seconds
                            enhanced_data_point['photo_volt'],
                            enhanced_data_point['absorbance'],
                            enhanced_data_point['concentration'],
                            enhanced_data_point['ec_volt'],
                            enhanced_data_point['ec_mscm'],
                            enhanced_data_point['ph_volt'],
                            enhanced_data_point['ph_value'],
                            enhanced_data_point['nitrate_volt'],
                            0.0,  # Nitrate PPM placeholder
                            enhanced_data_point['temperature']
                        ]
                        
                        with lock:
                            global_data.append(legacy_values)
                        
                        # Update health monitoring timestamp
                        update_data_timestamp()
                        
                        last_sensor_values = legacy_values
                        
                        # Write to CSV with enhanced event info
                        event_info = f"Enhanced-Cycle:{enhanced_data_point['cycle_id']}-Event:{enhanced_data_point['event_num']}-Stage:{enhanced_data_point['stage']}"
                        csv_writer.writerow(legacy_values + [event_info])
                        csv_file.flush()
                        
                        print(f"📊 SENSOR: Cycle {enhanced_data_point['cycle_id']}, pH={enhanced_data_point['ph_value']:.2f}, EC={enhanced_data_point['ec_mscm']:.2f} mS/cm")
                    
                    elif data_type == 'EVENT':
                        enhanced_data['events'].append(enhanced_data_point)
                        print(f"🎯 EVENT: {enhanced_data_point['event_type']} #{enhanced_data_point['event_number']} - {enhanced_data_point['action']} (pH={enhanced_data_point['ph_measurement']:.2f}, EC={enhanced_data_point['ec_measurement']:.2f})")
                    
                    elif data_type == 'STATUS':
                        enhanced_data['status'].append(enhanced_data_point)
                        ph_status = "✅" if enhanced_data_point['ph_within_tolerance'] else "❌"
                        ec_status = "✅" if enhanced_data_point['ec_within_tolerance'] else "❌"
                        print(f"📈 STATUS: Stage {enhanced_data_point['stage']}, pH{ph_status} EC{ec_status}, Health={enhanced_data_point['system_health']}%")
                    
                    elif data_type == 'DOSING_CALC':
                        enhanced_data['dosing_calc'].append(enhanced_data_point)
                        if enhanced_data_point['pump_type'] != 'none':
                            print(f"⚗️ DOSING: {enhanced_data_point['pump_type']} - {enhanced_data_point['adjusted_volume']:.2f}mL ({enhanced_data_point['dosing_time_ms']}ms) for pH {enhanced_data_point['current_ph']:.2f}→{enhanced_data_point['target_ph']:.1f}")
                        else:
                            print(f"✅ NO DOSING: pH={enhanced_data_point['current_ph']:.2f}, EC={enhanced_data_point['current_ec']:.2f} within tolerance")
                    
                    continue
                
                # Fall back to legacy format processing
                # Process event line
                process_event_line(line)
                
                # Detect pH/EC messages directly in lines
                if "PRGSample pH measurement" in line:
                    current_action = "PRGSample pH measurement"
                    pending_ph_measurement = True
                    print("🧪 Detected PRGSample pH measurement – aguardando nova leitura de sensor")
                
                if "PRGSample EC measurement" in line:
                    current_action = "PRGSample EC measurement"
                    pending_ec_measurement = True
                    print("⚡ Detected PRGSample EC measurement – aguardando nova leitura de sensor")
                
                # Skip enhanced format lines (with emojis and human-readable text)
                if line.startswith(('📊', '📈', '⚗️', '🔄', '💧', '⚡', '🌡️', '🧪')):
                    continue
                
                # Process sensor data lines (raw CSV format only)
                parts = line.split(',')
                if len(parts) >= 11 and parts[0].replace('.', '').isdigit():  # Ensure first part is numeric (timestamp)
                    try:
                        values = [float(part) for part in parts[:11]]
                        with lock:
                            global_data.append(values)
                        
                        # Update health monitoring timestamp
                        update_data_timestamp()
                        
                        # Store the last valid sensor values
                        last_sensor_values = values
                        
                        # Write to time-based CSV
                        csv_writer.writerow(values + [""])
                        csv_file.flush()
                        
                        # Uso do sensor data lido agora se houver evento pendente
                        if pending_ph_measurement:
                            cycle_num = current_prgsample_count if current_prgsample_count else 1
                            event_action_key = f"PRGSample_pH_measurement_{cycle_num}"
                            if event_action_key not in event_processed_keys:
                                event_csv_writer.writerow([
                                    cycle_num,
                                    "PRGSample",
                                    current_event_num if current_event_num is not None else 5,
                                    "PRGSample pH measurement",
                                    values[0],       # usa os valores da nova linha
                                    "",
                                    values[4],
                                    values[5],
                                    values[6],
                                    values[7],
                                    values[8],
                                    values[9]
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
                                    cycle_num,
                                    "PRGSample",
                                    current_event_num if current_event_num is not None else 5,
                                    "PRGSample EC measurement",
                                    values[0],
                                    "",
                                    values[4],
                                    values[5],
                                    values[6],
                                    values[7],
                                    values[8],
                                    values[9]
                                ])
                                event_csv_file.flush()
                                event_processed_keys.add(event_action_key)
                                print(f"✅ Recorded deferred EC measurement data for cycle {cycle_num}")
                            pending_ec_measurement = False
                        
                        # If we're in an event, store these values for the event
                        if current_event_type and current_event_num is not None:
                            event_key = f"{current_event_type}_{current_event_num}"
                            # Extrair os valores que queremos registrar, incluindo o timestamp (values[0])
                            event_measurements[event_key] = [
                                values[0],  # Time, exatamente o mesmo do sensor_data
                                values[4],  # EC (V)
                                values[5],  # EC (ppm)
                                values[6],  # pH (V)
                                values[7],  # pH Value
                                values[8],  # Nitrate (V)
                                values[9]   # Nitrate (ppm)
                            ]
                        
                        # Quando detectar um evento com sensor data
                        if (current_event_type and current_event_num is not None and current_action is not None 
                            and current_action not in ["PRGSample pH measurement", "PRGSample EC measurement"]):
                            # Determinar o número de ciclo correto
                            cycle_num = None
                            if current_event_type == "PRGCal":
                                cycle_num = current_prgcal_count
                            elif current_event_type == "PRGSample":
                                cycle_num = current_prgsample_count
                            
                            # Escrever no event_data.csv usando o timestamp do sensor (assumindo que 'values' é o registro atual)
                            event_action_key = f"{current_event_type}_{current_event_num}_{current_action}"
                            if event_action_key not in event_processed_keys:
                                event_csv_writer.writerow([
                                    cycle_num,                    # Cycle Number
                                    current_event_type,           # Event Type
                                    current_event_num,            # Event
                                    current_action,               # Action
                                    values[0],                    # Time: utiliza o mesmo timestamp usado em sensor_data.csv
                                    "",                           # Dosing Time (s)
                                    values[4] if len(values) > 4 else 0.0,  # EC (V)
                                    values[5] if len(values) > 5 else 0.0,  # EC (ppm)
                                    values[6] if len(values) > 6 else 0.0,  # pH (V)
                                    values[7] if len(values) > 7 else 0.0,  # pH Value
                                    values[8] if len(values) > 8 else 0.0,  # Nitrate (V)
                                    values[9] if len(values) > 9 else 0.0   # Nitrate (ppm)
                                ])
                                event_csv_file.flush()
                                event_processed_keys.add(event_action_key)
                                print(f"✅ Recorded event data for {current_event_type} #{current_event_num}, Cycle {cycle_num}, Action: {current_action}")
                                current_action = None
                        
                    except ValueError as ve:
                        print(f"Error converting data: {ve}")
                else:
                    # Registrar eventos de dosagem se presentes
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
                            cycle_num,         # Cycle Number
                            "Dosing",          # Event Type
                            "",                # Event (não aplicável)
                            dosing_action,     # Action: descrição da dosagem
                            "",                # Time: sem timestamp de sensor
                            dosing_time_s,     # Dosing Time (s)
                            "", "", "", "", "", ""
                        ])
                        event_csv_file.flush()
                        print(f"✅ Recorded dosing event: {dosing_action}, dosing time: {dosing_time_s} s")
                    else:
                        # ALTERAÇÃO: Registrar TODOS eventos para o event_data.csv
                        # Verificar se são mensagens de dosagem (já estamos tratando)
                        if "Dosing:" in line:
                            # Código existente para dosagem - não alterado
                            dosing_match = re.search(r'Dosing:\s*(.+?)\s+for\s+(\d+)ms', line)
                            if dosing_match:
                                # ...código existente...
                                pass
                        else:
                            # NOVO CÓDIGO - registrar todos os outros eventos
                            should_log = True
                            dosing_patterns = [
                                '{"action":"dose"',
                                '"action":"dosing_start"',
                                '"action":"dosing_complete"',
                                'Activating pump on pin',
                                'Pump deactivated',
                                'Received command:'
                            ]
                            
                            # Check if line contains any dosing-related pattern
                            for pattern in dosing_patterns:
                                if pattern in line:
                                    should_log = False
                                    break
                            
                            # Only log non-dosing messages
                            if should_log:
                                with lock:
                                    event_data.append(line)
                                
                                # NOVO - Escrever para o event_data.csv também
                                event_action_key = f"Event_{len(event_data)}"
                                if event_action_key not in event_processed_keys:
                                    # Detectar tipo de evento usando regex
                                    event_type = ""
                                    event_num = ""
                                    
                                    # Verificar se é um evento PRG
                                    prg_match = re.search(r'PRG(\w+)\s+Event\s+#(\d+)', line)
                                    if prg_match:
                                        event_type = f"PRG{prg_match.group(1)}"
                                        event_num = prg_match.group(2)
                                    
                                    # Escrever no event_data.csv sem valores de sensores
                                    event_csv_writer.writerow([
                                        current_cycle_num if current_cycle_num is not None else "",  # Cycle Number
                                        event_type,          # Event Type
                                        event_num,           # Event
                                        line.strip(),        # Action: texto completo do evento
                                        "",                  # Time (vazio para eventos sem timestamp)
                                        "",                  # Dosing Time (vazio)
                                        "", "", "", "", "", "" # Valores de sensores vazios
                                    ])
                                    event_csv_file.flush()
                                    event_processed_keys.add(event_action_key)
                                
                                # Write event to time-based CSV with empty sensor data (código existente)
                                empty_sensor_data = [""] * 11
                                csv_writer.writerow(empty_sensor_data + [line])
                                csv_file.flush()
                
    except Exception as e:
        log_connection_status(f"Error reading data from PlatformIO: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        
        # Mark connection as unhealthy and attempt recovery
        global connection_healthy
        connection_healthy = False
        
        # Wait before attempting recovery
        time.sleep(5)
        
        # The health monitor will detect this and attempt recovery
        log_connection_status("Monitoring subprocess crashed - health monitor will attempt recovery", "WARNING")

def periodic_event_data_saver():
    global event_measurements, event_csv_writer
    print("Periodic event data saver running...")
    
    processed_events = set()  # Rastreamento dos eventos já salvos
    
    while True:
        time.sleep(60)  # A cada minuto
        print("Running periodic event data save check")
        
        with lock:
            for event_key, measurements in list(event_measurements.items()):
                if event_key not in processed_events and measurements:
                    event_type, event_num = event_key.split('_')
                    
                    cycle_num = None
                    if event_type == "PRGCal":
                        cycle_num = current_prgcal_count
                    elif event_type == "PRGSample":
                        cycle_num = current_prgsample_count
                    
                    # Aqui, measurements[0] é o timestamp do sensor (igual ao usado em sensor_data.csv)
                    event_csv_writer.writerow([
                        cycle_num,        # Cycle Number
                        event_type,       # Event Type
                        event_num,        # Event
                        "",               # Action
                        measurements[0],  # Time: valor do timestamp do sensor
                        "",               # Dosing Time (s)
                        measurements[1],  # EC (V)
                        measurements[2],  # EC (ppm)
                        measurements[3],  # pH (V)
                        measurements[4],  # pH Value
                        measurements[5],  # Nitrate (V)
                        measurements[6]   # Nitrate (ppm)
                    ])
                    print(f"💾 Periodic save: {event_key} - {measurements}")
                    processed_events.add(event_key)
                    del event_measurements[event_key]
            event_csv_file.flush()

def generate_event_sync_data(sensor_file, output_file):
    """Gera um arquivo de sincronização que combina dados de sensores com eventos"""
    try:
        print(f"Generating event sync data from {sensor_file} to {output_file}")
        
        # Não fazer nada se o arquivo não existe
        if not os.path.exists(sensor_file):
            print(f"Source file not found: {sensor_file}")
            return
            
        # Ler os dados do sensor
        sensor_data = {}
        with open(sensor_file, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)  # Skip headers
            for row in reader:
                if len(row) >= 11 and all(row[:11]):  # Only consider rows with sensor data
                    try:
                        timestamp = float(row[0])
                        sensor_data[timestamp] = row[:11]  # Store only sensor values
                    except (ValueError, IndexError):
                        continue
        
        # Agora escrever para arquivo de saída com cabeçalho
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Time (ms)', 
                'Event Type',
                'Event Number',
                'Cycle Number',
                'Photoresistor (V)', 'Abs (a.u.)', 'Conc (ppm)',
                'EC (V)', 'EC (mS/cm)', 'pH (V)', 'pH Value',
                'Nitrate (V)', 'Nitrate (ppm)', 'Temp(°C)'
            ])
            
            # Ordenar os timestamps e escrever os dados
            for timestamp in sorted(sensor_data.keys()):
                row_data = sensor_data[timestamp]
                # Procurar por eventos que correspondam ao timestamp (simplificado)
                event_type = ""
                event_num = ""
                cycle_num = ""
                
                # Escrever linha com dados do sensor
                writer.writerow([
                    row_data[0],  # Time
                    event_type,   # Event Type
                    event_num,    # Event Number
                    cycle_num,    # Cycle Number
                    row_data[1],  # Photoresistor
                    row_data[2],  # Absorbance
                    row_data[3],  # Concentration
                    row_data[4],  # EC Voltage
                    row_data[5],  # EC ppm
                    row_data[6],  # pH Voltage
                    row_data[7],  # pH Value
                    row_data[8],  # Nitrate Voltage
                    row_data[9],  # Nitrate ppm
                    row_data[10]  # Temperature
                ])
        
        print(f"✅ Event sync data generation complete: {output_file}")
    except Exception as e:
        print(f"❌ Error generating event sync data: {e}")
        import traceback
        traceback.print_exc()

def rotate_log_files():
    global csv_file, csv_writer, event_csv_file, event_csv_writer, current_time_global
    while True:
        time.sleep(3600)  # Every hour
        print("Rotating log files...")
        
        # Keep reference to previous timestamp
        prev_time = current_time_global
        
        # Close existing files
        if csv_file:
            csv_file.close()
        if event_csv_file:
            event_csv_file.close()
            
        # Create new files with timestamp
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        current_time_global = current_time
        
        csv_filename = os.path.join(DATA_DIR, f'sensor_data_{current_time}.csv')
        csv_file = open(csv_filename, 'w', newline='')
        csv_writer = csv.writer(csv_file)
        
        # Write headers
        csv_writer.writerow([
            'Time (ms)', 'Photoresistor (V)', 'Abs (a.u.)', 'Conc (ppm)',
            'EC (V)', 'EC (mS/cm)', 'pH (V)', 'pH Value',
            'Nitrate (V)', 'Nitrate (ppm)', 'Temp(°C)', 'Event Info'
        ])
        
        # Create new event CSV
        event_csv_filename = os.path.join(DATA_DIR, f'event_data_{current_time}.csv')
        event_csv_file = open(event_csv_filename, 'w', newline='')
        event_csv_writer = csv.writer(event_csv_file)
        event_csv_writer.writerow([
            'Cycle Number',
            'Event Type',
            'Event',
            'Action',
            'Time',
            'Dosing Time (s)',
            'EC (V)',
            'EC (ppm)',
            'pH (V)',
            'pH Value',
            'Nitrate (V)',
            'Nitrate (ppm)'
        ])
        
        # Create new extracted_cycle_data file
        extracted_filename = os.path.join(DATA_DIR, f'extracted_cycle_data_{current_time}.csv')
        with open(extracted_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Event Type', 'Cycle Number', 'Time',
                'EC (V)', 'EC (mS/cm)', 'pH (V)', 'pH Value', 
                'Nitrate (V)', 'Nitrate (ppm)'
            ])
        
        # Generate event sync data from the previous sensor data file
        prev_sensor_file = os.path.join(DATA_DIR, f'sensor_data_{prev_time}.csv')
        event_sync_filename = os.path.join(DATA_DIR, f'event_sync_data_{prev_time}.csv')
        
        # Generate event sync data in background
        threading.Thread(target=generate_event_sync_data, 
                         args=(prev_sensor_file, event_sync_filename),
                         daemon=True).start()
        
        print(f"Rotated log files and initiated event sync data generation")

def start_monitor_thread():
    print("Starting monitor thread...")
    thread = threading.Thread(target=read_data_from_platformio)
    thread.daemon = True
    thread.start()
    return thread

def start_periodic_saver_thread():
    print("Starting periodic saver thread...")
    thread = threading.Thread(target=periodic_event_data_saver)
    thread.daemon = True
    thread.start()
    return thread

def start_log_rotation_thread():
    print("Starting log rotation thread...")
    thread = threading.Thread(target=rotate_log_files)
    thread.daemon = True
    thread.start()
    return thread

def start_health_monitor_thread():
    print("Starting health monitor thread...")
    thread = threading.Thread(target=health_monitor_thread)
    thread.daemon = True
    thread.start()
    return thread

# Modify the create_graph_with_controls function, around line 204:
def create_graph_with_controls(graph_id, graph_title):
    """Create a graph with y-axis controls"""
    return html.Div([
        html.H4(graph_title),
        html.Div([
            html.Div([
                html.Label("Center Point:", style={'marginRight': '10px', 'fontSize': '14px'}),
                dcc.Input(
                    id=f'{graph_id}-center-input',
                    type='number',
                    placeholder='Auto',
                    step=0.01,  # Changed from 0.1 to 0.01 for finer control
                    style={'width': '80px'}
                ),
            ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%'}),
            
            html.Div([
                html.Label("Signal Range:", style={'marginRight': '10px', 'fontSize': '14px'}),
                dcc.Input(
                    id=f'{graph_id}-signal-input',
                    type='number',
                    min=0.001,
                    max=20,
                    step=0.001,
                    value=1,
                    style={'width': '80px'}
                ),
            ], style={'width': '48%', 'display': 'inline-block'}),
        ], style={'margin': '5px 0', 'padding': '5px', 'backgroundColor': '#f8f9fa', 'borderRadius': '5px'}),
        dcc.Graph(id=graph_id),
    ], style={'marginBottom': '30px'})

# Use the v5p4 layout with global time window but add our y-axis controls
app = dash.Dash(__name__)
app.layout = html.Div([
    html.H1("Sensor Dashboard"),
    
    # Connection Status Panel
    html.Div([
        html.H4("🔍 Connection Health Monitor", style={'margin': '0', 'color': '#2c3e50'}),
        html.Div([
            html.Div([
                html.Span("Status: ", style={'fontWeight': 'bold'}),
                html.Span(id='connection-status', children="🔄 Initializing...", style={'marginLeft': '10px'})
            ], style={'marginBottom': '10px'}),
            html.Div([
                html.Span("Port: ", style={'fontWeight': 'bold'}),
                html.Span(id='current-port', children=current_serial_port, style={'marginLeft': '10px', 'fontFamily': 'monospace'})
            ], style={'marginBottom': '10px'}),
            html.Div([
                html.Span("Last Data: ", style={'fontWeight': 'bold'}),
                html.Span(id='last-data-time', children="No data yet", style={'marginLeft': '10px'})
            ], style={'marginBottom': '5px'}),
        ]),
        html.Details([
            html.Summary("📋 Connection Log", style={'cursor': 'pointer', 'fontWeight': 'bold'}),
            html.Div(id='connection-log', style={
                'maxHeight': '120px', 
                'overflowY': 'scroll', 
                'backgroundColor': '#f8f9fa',
                'padding': '8px',
                'border': '1px solid #dee2e6',
                'borderRadius': '4px',
                'fontFamily': 'monospace',
                'fontSize': '12px',
                'marginTop': '5px'
            })
        ], style={'marginTop': '10px'})
    ], style={
        'margin': '10px 0', 
        'padding': '15px', 
        'backgroundColor': '#e8f4fd', 
        'borderRadius': '8px',
        'border': '1px solid #b8daff'
    }),
    
    # Global time window control from v5p4
    html.Div([
        html.Div([
            html.Label("Tamanho da Janela de Tempo (segundos):", style={'marginRight': '10px'}),
            dcc.Slider(
                id='time-window-slider',
                min=5,
                max=28800,
                step=5,
                value=60,
                marks={i: f'{i}s' for i in [5, 30, 60, 120, 180, 240, 300]},
                tooltip={"placement": "bottom", "always_visible": True}
            ),
            # Add visualization mode selector
            html.Div([
                html.Label("Visualization Mode:", style={'marginRight': '10px', 'marginTop': '15px'}),
                dcc.RadioItems(
                    id='viz-mode-selector',
                    options=[
                        {'label': 'Full data', 'value': 'full'},       # Renamed from 'traveling'
                        {'label': 'Window', 'value': 'window'}         # Renamed from 'full'
                    ],
                    value='window',  # Default to full data
                    inline=True
                )
            ], style={'marginTop': '10px'})
        ], style={'width': '80%', 'display': 'inline-block', 'verticalAlign': 'middle'}),
        
        html.Div([
            html.Button('Save All Event Data', id='save-event-data', n_clicks=0),
            html.Div(id='save-status', style={'marginLeft': '15px', 'display': 'inline-block'})
        ], style={'width': '20%', 'display': 'inline-block', 'verticalAlign': 'middle', 'textAlign': 'right'})
    ], style={'margin': '20px 0', 'padding': '10px', 'backgroundColor': '#f8f9fa', 'borderRadius': '5px'}),
    
    # Replace simple graphs with our enhanced graph controls
    create_graph_with_controls('graph-photoresistor', 'Photoresistor (V)'),
    create_graph_with_controls('graph-absorbance', 'Absorbance (a.u.)'),
    create_graph_with_controls('graph-concentration', 'Concentration (ppm)'),
    create_graph_with_controls('graph-ec-voltage', 'EC Voltage (V)'),
    create_graph_with_controls('graph-ec-ppm', 'EC (mS/cm)'),  # Changed from 'EC (ppm)'
    create_graph_with_controls('graph-ph-voltage', 'pH Voltage (V)'),
    create_graph_with_controls('graph-ph-value', 'pH Value'),
    create_graph_with_controls('graph-nitrate-voltage', 'Nitrate Voltage (V)'),
    create_graph_with_controls('graph-nitrate-value', 'Nitrate (ppm)'),
    create_graph_with_controls('graph-temperature', 'Temperature (°C)'),
    
    dcc.Interval(id='interval-component', interval=1*1000, n_intervals=0),
    
    html.H3("Event Log (all entries)"),
    html.Div(id='event-log', style={
        'whiteSpace': 'pre-wrap',
        'overflowY': 'scroll',
    })
])

# Callback for connection status updates
@app.callback(
    [Output('connection-status', 'children'),
     Output('current-port', 'children'),
     Output('last-data-time', 'children'),
     Output('connection-log', 'children')],
    [Input('interval-component', 'n_intervals')]
)
def update_connection_status(n_intervals):
    global connection_healthy, current_serial_port, last_data_received, connection_status_log
    
    # Connection status with emoji
    if connection_healthy:
        status_text = "✅ Connected"
        status_color = "#28a745"
    else:
        status_text = "❌ Disconnected"
        status_color = "#dc3545"
    
    # Format last data time
    if last_data_received:
        time_diff = (datetime.now() - last_data_received).total_seconds()
        if time_diff < 60:
            last_data_text = f"{time_diff:.0f}s ago"
        elif time_diff < 3600:
            last_data_text = f"{time_diff/60:.1f}min ago"
        else:
            last_data_text = f"{time_diff/3600:.1f}h ago"
    else:
        last_data_text = "No data received"
    
    # Connection log entries (newest first)
    log_entries = []
    for entry in reversed(connection_status_log[-10:]):  # Show last 10 entries
        log_entries.append(html.Div(entry, style={'margin': '2px 0'}))
    
    return (
        html.Span(status_text, style={'color': status_color, 'fontWeight': 'bold'}),
        current_serial_port,
        last_data_text,
        log_entries
    )

# Callback para atualizar os gráficos
@app.callback(
    [Output('graph-photoresistor', 'figure'),
     Output('graph-absorbance', 'figure'),
     Output('graph-concentration', 'figure'),
     Output('graph-ec-voltage', 'figure'),
     Output('graph-ec-ppm', 'figure'),
     Output('graph-ph-voltage', 'figure'),
     Output('graph-ph-value', 'figure'),
     Output('graph-nitrate-voltage', 'figure'),
     Output('graph-nitrate-value', 'figure'),
     Output('graph-temperature', 'figure')],
    [Input('interval-component', 'n_intervals'),
     Input('time-window-slider', 'value'),
     Input('viz-mode-selector', 'value'),
     Input('graph-photoresistor-center-input', 'value'),
     Input('graph-photoresistor-signal-input', 'value'),
     Input('graph-absorbance-center-input', 'value'),
     Input('graph-absorbance-signal-input', 'value'),
     Input('graph-concentration-center-input', 'value'),
     Input('graph-concentration-signal-input', 'value'),
     Input('graph-ec-voltage-center-input', 'value'),
     Input('graph-ec-voltage-signal-input', 'value'),
     Input('graph-ec-ppm-center-input', 'value'),
     Input('graph-ec-ppm-signal-input', 'value'),
     Input('graph-ph-voltage-center-input', 'value'),
     Input('graph-ph-voltage-signal-input', 'value'),
     Input('graph-ph-value-center-input', 'value'),
     Input('graph-ph-value-signal-input', 'value'),
     Input('graph-nitrate-voltage-center-input', 'value'),
     Input('graph-nitrate-voltage-signal-input', 'value'),
     Input('graph-nitrate-value-center-input', 'value'),
     Input('graph-nitrate-value-signal-input', 'value'),
     Input('graph-temperature-center-input', 'value'),
     Input('graph-temperature-signal-input', 'value')]
)
def update_graphs(n_intervals, time_window, viz_mode, *axis_controls):
    with lock:
        # Convert deque to list for processing
        data = list(global_data)
    
    # Se não temos dados, retorne gráficos vazios
    if not data:
        return [{'data': [], 'layout': {'title': 'No data available'}}] * 10
    
    # Usar diretamente os valores de tempo
    time_ms = [d[0] for d in data]
    time_sec = time_ms  # Usar os valores brutos sem converter para segundos
    
    # Valores dos sensores
    photoresistor = [d[1] for d in data] 
    absorbance = [d[2] for d in data]    
    concentration = [d[3] for d in data]  
    ec_voltage = [d[4] for d in data]     
    ec_ppm = [d[5] for d in data]         
    ph_voltage = [d[6] for d in data]     
    ph_value = [d[7] for d in data]       
    nitrate_voltage = [d[8] for d in data]  
    nitrate_ppm = [d[9] for d in data]    
    temperature = [d[10] for d in data]   
    
    # Determinar o range de tempo a usar
    if viz_mode == 'window' and len(time_sec) > 0:  
        if time_sec[-1] > time_window:
            x_range = [time_sec[-1] - time_window, time_sec[-1]]
        else:
            x_range = [0, max(time_window, time_sec[-1])]
    else:  # 'full' mode (show all data)
        if len(time_sec) > 0:
            x_range = [0, time_sec[-1]]
        else:
            x_range = [0, time_window]
    
    # Extract the y-axis control values and create graphs
    figures = []
    data_sets = [photoresistor, absorbance, concentration, 
                 ec_voltage, ec_ppm, ph_voltage, ph_value, 
                 nitrate_voltage, nitrate_ppm, temperature]
    
    titles = ['Photoresistor (V)', 'Absorbance (a.u.)', 'Concentration (ppm)', 
              'EC Voltage (V)', 'EC (mS/cm)', 'pH Voltage (V)', 'pH Value', 
              'Nitrate Voltage (V)', 'Nitrate (ppm)', 'Temperature (°C)']
    
    # Process each graph with its y-axis controls
    for i, (y_data, title) in enumerate(zip(data_sets, titles)):
        # Get center and range values for this graph from axis_controls
        center_value = axis_controls[i*2]  # Every even index
        signal_range = axis_controls[i*2+1]  # Every odd index
        
        # Calculate y-axis range
        if center_value is not None and signal_range is not None:
            y_min = center_value - signal_range
            y_max = center_value + signal_range
        else:
            # Usar a lógica mais adaptável 
            if y_data:
                y_min_data = min(y_data)
                y_max_data = max(y_data)
                y_center = (y_min_data + y_max_data) / 2
                base_range = max(y_max_data - y_min_data, max(0.05, abs(y_center * 0.05)))
                applied_range = base_range * (signal_range or 1.0)  
                y_min = max(0, y_center - applied_range/2)
                y_max = y_center + applied_range/2
            else:
                y_min = 0
                y_max = 1
        
        # Create figure
        fig = {
            'data': [
                {'x': time_sec, 'y': y_data, 'type': 'line', 'name': title}
            ],
            'layout': {
                'title': title,
                'xaxis': {'title': 'Time (s)', 'range': x_range},
                'yaxis': {'title': title, 'range': [y_min, y_max]},
                'margin': {'l': 50, 'b': 50, 't': 30, 'r': 50},
                'legend': {'x': 0, 'y': 1},
                'height': 350,
            }
        }
        figures.append(fig)
    
    return figures

# Callback para atualizar o log de eventos
@app.callback(
    Output('event-log', 'children'),
    Input('interval-component', 'n_intervals')
)
def update_event_log(n_intervals):
    with lock:
        all_logs = event_data
    
    return "\n".join(all_logs)

# Callback para o botão de salvar dados
@app.callback(
    Output('save-status', 'children'),
    Input('save-event-data', 'n_clicks')
)
def save_all_event_data(n_clicks):
    if n_clicks == 0:
        return ""
    
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"all_event_data_{timestamp}.csv"
        
        with open(os.path.join(DATA_DIR, filename), 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Event Type", "Event Number", "Data..."]);
            
            for event_key, measurements in event_measurements.items():
                if measurements:
                    event_type, event_num = event_key.split('_');
                    writer.writerow([event_type, event_num] + measurements);
        
        return f"✅ Saved to {filename}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# Adicionar global de controle de timestamp para rotação de logs
current_time_global = datetime.now().strftime("%Y%m%d_%H%M%S")

if __name__ == '__main__':
    print("Starting dashboard...")
    
    # Write initial health status
    write_health_status()
    
    # Iniciar threads
    monitor_thread = start_monitor_thread()
    saver_thread = start_periodic_saver_thread()
    rotation_thread = start_log_rotation_thread()
    health_thread = start_health_monitor_thread()
    print("Started monitoring, data saving, log rotation, and health monitoring threads")
    
    # Iniciar thread ZMQ
    zmq_thread = threading.Thread(target=zmq_communication_thread)
    zmq_thread.daemon = True
    zmq_thread.start()
    print("Started ZMQ communication thread")
    
    # Dar tempo para as threads iniciarem
    time.sleep(2)
    
    # Write health status after threads start
    write_health_status()
    
    # Iniciar o servidor Dash
    print("Starting Dash server on port 8050...")
    app.run(debug=False, host='0.0.0.0', port=8050)
    
    # Fechar arquivos ao sair
    if csv_file:
        csv_file.close()
        print("CSV file closed.")
    
    if event_csv_file:
        event_csv_file.close()
        print("Event CSV file closed.")

def listen_coefficient_updates(serial_port='/dev/ttyUSB1', baudrate=115200):
    pattern = re.compile(r'COEFFICIENT_UPDATE,(\d+),([\w_]+),([\d.]+),([\d.\-]+),([\d.\-]+),([\d.]+)')
    with serial.Serial(serial_port, baudrate, timeout=1) as ser:
        while True:
            line = ser.readline().decode(errors='ignore').strip()
            match = pattern.match(line)
            if match:
                ts, pump, coeff, expected, observed, lr = match.groups()
                print(f"[COEFFICIENT UPDATE] Time: {ts} | Pump: {pump} | New Coefficient: {coeff} | Expected: {expected} | Observed: {observed} | Learning Rate: {lr}")
