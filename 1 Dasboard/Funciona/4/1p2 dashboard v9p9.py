import time
import csv
import os
import subprocess
import threading
import queue
import copy
import re
import zmq
from datetime import datetime
from dash import dcc, html
from dash.dependencies import Output, Input
import dash
import plotly.graph_objs as go
import sys
import dash_bootstrap_components as dbc
import serial
import json

# CONFIGURATION
SERIAL_PORT = '/dev/cu.usbserial-110'
BAUD_RATE = 115200
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# ZMQ communication for dosing controller
context = zmq.Context()
dosing_socket = context.socket(zmq.REP)
dosing_socket.bind("tcp://*:5555")

# Function to send command to ESP32 via serial
def send_command_to_esp32(command):
    """Envia comando para o ESP32 via serial e retorna a resposta"""
    try:
        # Abrir conexão serial
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2) as ser:
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

# Global data storage
global_data = []
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
        current_action = "PRGSample pH measurement"
        # Não resetar current_event_type ou current_event_num
        print(f"🧪 Detected PRGSample pH measurement")
        return None
    
    # Associar EC measurement ao evento PRGSample
    if "PRGSample EC measurement" in line:
        current_action = "PRGSample EC measurement"
        # Não resetar current_event_type ou current_event_num
        print(f"⚡ Detected PRGSample EC measurement")
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
    global global_data, event_data, current_prgcal_count, current_prgsample_count
    global current_event_type, current_event_num, event_measurements, current_action, current_cycle_num
    
    try:
        print("Starting PlatformIO monitor subprocess...")
        process = subprocess.Popen(
            ['pio', 'device', 'monitor', '--port', SERIAL_PORT, '--baud', str(BAUD_RATE)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        
        last_sensor_values = None
        
        while True:
            line = process.stdout.readline().decode('utf-8').strip()
            if line:
                # Process event line
                process_event_line(line)
                
                # Detect pH/EC messages directly in lines
                if "PRGSample pH measurement" in line:
                    current_action = "PRGSample pH measurement"
                    print(f"🧪 Detected PRGSample pH measurement in raw line")
                    
                    # If we have sensor values, write immediately to CSV
                    if last_sensor_values and len(last_sensor_values) > 4:
                        cycle_num = current_prgsample_count if current_prgsample_count else 1
                        event_action_key = f"PRGSample_pH_measurement_{cycle_num}"
                        
                        if event_action_key not in event_processed_keys:
                            event_csv_writer.writerow([
                                cycle_num,                                 # Cycle Number
                                "PRGSample",                               # Event Type
                                current_event_num if current_event_num is not None else 5,  # Event
                                "PRGSample pH measurement",                # Action
                                int(last_sensor_values[0]),                # Time (timestamp em segundos)
                                "",                                        # Dosing Time (s)
                                last_sensor_values[4],                     # EC (V)
                                last_sensor_values[5],                     # EC (ppm)
                                last_sensor_values[6],                     # pH (V)
                                last_sensor_values[7],                     # pH Value
                                last_sensor_values[8],                     # Nitrate (V)
                                last_sensor_values[9]                      # Nitrate (ppm)
                            ])
                            event_csv_file.flush()
                            event_processed_keys.add(event_action_key)
                            print(f"✅ Recorded pH measurement data for cycle {cycle_num}")
                
                if "PRGSample EC measurement" in line:
                    current_action = "PRGSample EC measurement"
                    print(f"⚡ Detected PRGSample EC measurement in raw line")
                    
                    # If we have sensor values, write immediately to CSV
                    if last_sensor_values and len(last_sensor_values) > 4:
                        cycle_num = current_prgsample_count if current_prgsample_count else 1
                        event_action_key = f"PRGSample_EC_measurement_{cycle_num}"
                        
                        if event_action_key not in event_processed_keys:
                            event_csv_writer.writerow([
                                cycle_num,                                 # Cycle Number
                                "PRGSample",                               # Event Type
                                current_event_num if current_event_num is not None else 5,  # Event
                                "PRGSample EC measurement",                # Action
                                int(last_sensor_values[0]),                # Time (timestamp em segundos)
                                "",                                        # Dosing Time (s)
                                last_sensor_values[4],                     # EC (V)
                                last_sensor_values[5],                     # EC (ppm)
                                last_sensor_values[6],                     # pH (V)
                                last_sensor_values[7],                     # pH Value
                                last_sensor_values[8],                     # Nitrate (V)
                                last_sensor_values[9]                      # Nitrate (ppm)
                            ])
                            event_csv_file.flush()
                            event_processed_keys.add(event_action_key)
                            print(f"✅ Recorded EC measurement data for cycle {cycle_num}")
                            
                            # Evita registos repetidos: desativa o evento
                            current_action = None
                
                # Process sensor data lines
                parts = line.split(',')
                if len(parts) >= 11:  # Sensor data line with 11 values
                    try:
                        values = [float(part) for part in parts[:11]]
                        with lock:
                            global_data.append(values)
                        
                        # Store the last valid sensor values
                        last_sensor_values = values
                        
                        # Write to time-based CSV
                        csv_writer.writerow(values + [""])
                        csv_file.flush()
                        
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
                        if (current_event_type and current_event_num is not None and current_action is not None):
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
                                if current_action not in ["PRGSample pH measurement", "PRGSample EC measurement"]:
                                    current_action = None
                        
                    except ValueError as ve:
                        print(f"Error converting data: {ve}")
                else:
                    # FILTER OUT DOSING-RELATED JSON RESPONSES - THIS IS THE KEY CHANGE
                    should_log = True
                    
                    # Patterns to filter out
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
                    
                    # Only log the line if it's not a filtered dosing message
                    if should_log:
                        with lock:
                            event_data.append(line)
                        
                        # Write event to time-based CSV with empty sensor data
                        empty_sensor_data = [""] * 11
                        csv_writer.writerow(empty_sensor_data + [line])
                        csv_file.flush()
                
    except Exception as e:
        print(f"Error reading data from PlatformIO: {e}")
        import traceback
        traceback.print_exc()

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
    
    # Global time window control from v5p4
    html.Div([
        html.Div([
            html.Label("Tamanho da Janela de Tempo (segundos):", style={'marginRight': '10px'}),
            dcc.Slider(
                id='time-window-slider',
                min=5,
                max=300,
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
                    value='full',  # Default to full data
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
        'height': '400px',
        'border': '1px solid #ccc',
        'padding': '10px'
    }),
])

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
        data = copy.deepcopy(global_data)
    
    # Se não temos dados, retorne gráficos vazios
    if not data:
        return [{'data': [], 'layout': {'title': 'No data available'}}] * 10
    
    # Usar diretamente os valores de tempo (como na versão v7)
    time_ms = [d[0] for d in data]
    time_sec = time_ms  # Usar os valores brutos sem converter para segundos
    
    # Valores dos sensores
    photoresistor = [d[1] for d in data]  # index 1: photoresistor voltage
    absorbance = [d[2] for d in data]     # index 2: absorbance
    concentration = [d[3] for d in data]  # index 3: concentration
    ec_voltage = [d[4] for d in data]     # index 4: EC voltage
    ec_ppm = [d[5] for d in data]         # index 5: EC ppm
    ph_voltage = [d[6] for d in data]     # index 6: pH voltage
    ph_value = [d[7] for d in data]       # index 7: pH value
    nitrate_voltage = [d[8] for d in data]  # index 8: nitrate voltage
    nitrate_ppm = [d[9] for d in data]    # index 9: nitrate ppm
    temperature = [d[10] for d in data]   # index 10: temperature
    
    # Determinar o range de tempo a usar
    if viz_mode == 'window' and len(time_sec) > 0:  # 'window' mode (fixed window)
        if time_sec[-1] > time_window:
            # Mostrar apenas os dados dentro da janela de tempo
            x_range = [time_sec[-1] - time_window, time_sec[-1]]
        else:
            # Se ainda não temos dados suficientes, mostrar todo o range
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
            # Usar a lógica mais adaptável da versão v7
            if y_data:
                y_min_data = min(y_data)
                y_max_data = max(y_data)
                y_center = (y_min_data + y_max_data) / 2
                base_range = max(y_max_data - y_min_data, max(0.05, abs(y_center * 0.05)))
                applied_range = base_range * (signal_range or 1.0)  # Use o signal_range como escala
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
                'margin': {'l': 50, 'b': 50, 't': 30, 'r': 50},  # Usar as margens da versão v7
                'legend': {'x': 0, 'y': 1},
                'height': 350,  # Usar altura maior como na versão v7
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
        # Mostrar todos os eventos como na versão v7
        all_logs = event_data
    
    # Unir todos os logs com quebra de linha (sem numeração)
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
        # Create a timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"all_event_data_{timestamp}.csv"
        
        # Save to file
        with open(os.path.join(DATA_DIR, filename), 'w', newline='') as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(["Event Type", "Event Number", "Data..."])
            
            # Write event measurements
            for event_key, measurements in event_measurements.items():
                if measurements:
                    event_type, event_num = event_key.split('_')
                    writer.writerow([event_type, event_num] + measurements)
        
        return f"✅ Saved to {filename}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

if __name__ == '__main__':
    print("Starting dashboard...")
    
    # Iniciar threads
    monitor_thread = start_monitor_thread()
    saver_thread = start_periodic_saver_thread()
    rotation_thread = start_log_rotation_thread()
    print("Started monitoring and data saving threads")
    
    # Iniciar thread ZMQ para comunicação com o dosing controller
    zmq_thread = threading.Thread(target=zmq_communication_thread)
    zmq_thread.daemon = True
    zmq_thread.start()
    print("Started ZMQ communication thread")
    
    # Dar tempo para as threads iniciarem
    time.sleep(2)
    
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