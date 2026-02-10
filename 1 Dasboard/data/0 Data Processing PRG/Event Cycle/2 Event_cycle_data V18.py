import os
import csv
import re
import glob
from datetime import datetime
import tkinter as tk
from tkinter import filedialog

def show_file_picker(initial_dir):
    """Show file picker dialog to select sensor data file"""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    
    file_path = filedialog.askopenfilename(
        title="Select Sensor Data CSV File",
        initialdir=initial_dir,
        filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
    )
    
    return file_path

def extract_cycle_data(input_file, output_file):
    print(f"Processing {input_file}...")
    
    # Track state - improved tracking variables
    current_event_type = None
    current_cycle_num = None
    current_event_num = None  # Track event numbers separately
    measure_pending = False
    is_calibration_point = False
    
    # Store extracted data - modify the data structure
    extracted_data = []
    
    # Additional tracking for actions
    current_action = None
    dosing_time_s = None
    
    # Add look-ahead tracking variables
    looking_for_data = False
    look_ahead_limit = 10
    look_ahead_count = 0
    pending_event_data = None
    
    # Debug
    debug_mode = True  # Set to True to see detailed output
    
    with open(input_file, 'r', newline='') as csvfile:
        reader = csv.reader(csvfile)
        headers = next(reader)  # Skip header row
        
        # Store pending special events with their associated event number
        pending_special_events = []
        
        if debug_mode:
            print(f"CSV Headers: {headers}")
            print(f"Header count: {len(headers)}")
        
        # Encontrar índices das colunas necessárias - adaptação para novo formato
        time_col = 0  # Assume que "Time (ms)" é a primeira coluna
        ec_v_col = headers.index("EC (V)") if "EC (V)" in headers else 4
        ec_ppm_col = headers.index("EC (ppm)") if "EC (ppm)" in headers else 5
        ph_v_col = headers.index("pH (V)") if "pH (V)" in headers else 6
        ph_val_col = headers.index("pH Value") if "pH Value" in headers else 7
        nitrate_v_col = headers.index("Nitrate (V)") if "Nitrate (V)" in headers else 8
        nitrate_ppm_col = headers.index("Nitrate (ppm)") if "Nitrate (ppm)" in headers else 9
        event_info_col = headers.index("Event Info") if "Event Info" in headers else 10
        
        row_count = 0
        for row in reader:
            row_count += 1
            
            # Check if this is a special event info line (mostly empty except last column)
            if len(row) > event_info_col and all(not cell for cell in row[:event_info_col]) and row[event_info_col]:
                event_info = row[event_info_col]
                
                # First check if this is an event activation line
                event_match = re.search(r'PRG(\w+) Event #(\d+) activated', event_info)
                if event_match:
                    prg_type = event_match.group(1)
                    current_event_num = int(event_match.group(2))
                    current_event_type = f"PRG{prg_type}"
                    print(f"⚡ Event detected: {current_event_type} #{current_event_num}")
                    
                # Store special events with their current event context
                elif "pH measurement" in event_info:
                    # Save with the current event context
                    pending_special_events.append({
                        "action": "PRGSample pH measurement",
                        "event_type": current_event_type,
                        "event_num": current_event_num  # Link to the CURRENT event
                    })
                    print(f"📊 Found pH measurement for {current_event_type} #{current_event_num}")
                    
                elif "EC measurement" in event_info:
                    # Save with the current event context
                    pending_special_events.append({
                        "action": "PRGSample EC measurement",
                        "event_type": current_event_type,
                        "event_num": current_event_num  # Link to the CURRENT event
                    })
                    print(f"📊 Found EC measurement for {current_event_type} #{current_event_num}")
                
                # Add handling for dosing events
                elif "dosing" in event_info.lower():
                    # Extract dosing time if present
                    dosing_time_s = None
                    dosing_match = re.search(r'for (\d+)ms', event_info, re.IGNORECASE)
                    if dosing_match:
                        dosing_time_s = int(dosing_match.group(1)) / 1000.0  # Convert ms to seconds
                        
                    # Extract dosing substance (what's being dosed)
                    substance_match = re.search(r'Dosing: (\w+)', event_info, re.IGNORECASE)
                    substance = substance_match.group(1) if substance_match else "unknown"
                    
                    # Create action name with substance
                    action_name = f"Dosing: {substance}"
                        
                    # Save with the current event context
                    pending_special_events.append({
                        "action": action_name,
                        "event_type": current_event_type,
                        "event_num": current_event_num,  # Link to the CURRENT event
                        "dosing_time_s": dosing_time_s
                    })
                    print(f"💧 Found dosing event: {action_name} for {dosing_time_s}s in {current_event_type} #{current_event_num}")
            
            # Regular CSV data row processing
            # When we find a data row after a special event, associate them with their saved event number
            elif len(row) > ph_val_col and row[time_col] and pending_special_events:
                for special_event in pending_special_events:
                    # Process this data row with each pending special event
                    extracted_data.append([
                        current_cycle_num,            # Cycle Number
                        special_event["event_type"],   # Use saved event type
                        special_event["event_num"],    # Use saved event number
                        special_event["action"],       # Action
                        row[time_col],                 # Time
                        special_event.get("dosing_time_s"),  # Dosing Time (s)
                        float(row[ec_v_col]) if row[ec_v_col] else 0.0,  # EC (V)
                        float(row[ec_ppm_col]) if row[ec_ppm_col] else 0.0,  # EC (ppm)
                        float(row[ph_v_col]) if row[ph_v_col] else 0.0,  # pH (V)
                        float(row[ph_val_col]) if row[ph_val_col] and row[ph_val_col].lower() not in ['nan', 'inf'] else 0.0,  # pH Value
                        float(row[nitrate_v_col]) if row[nitrate_v_col] else 0.0,  # Nitrate (V)
                        float(row[nitrate_ppm_col]) if row[nitrate_ppm_col] else 0.0,  # Nitrate (ppm)
                    ])
                    print(f"✅ Associated {special_event['action']} with {special_event['event_type']} #{special_event['event_num']}")
                
                # Clear pending events after processing
                pending_special_events = []
            
            # Skip empty rows
            if not row or len(row) < 2:
                continue
            
            # Determine if this is a data row or event row
            has_event_info = False
            if len(row) > event_info_col and row[event_info_col]:  # Check if Event Info column has data
                # This has event info - process it
                event_info = row[event_info_col]
                has_event_info = True
                
                # Track dosing time if present
                dosing_time_s = None
                if "dosing" in event_info.lower() and "for" in event_info.lower() and "ms" in event_info.lower():
                    try:
                        # Extract dosing time in seconds
                        dosing_match = re.search(r'for (\d+)ms', event_info)
                        if dosing_match:
                            dosing_time_s = int(dosing_match.group(1)) / 1000.0  # Convert ms to seconds
                    except:
                        pass
                        
                # Track action types
                current_action = None
                
                # Debug event info for pattern matching
                if debug_mode:
                    print(f"Processing event info: '{event_info}'")
                
                if "pH calibration point" in event_info:
                    current_action = "pH calibration point"
                    measure_pending = True
                    is_calibration_point = True
                    print(f"📊 Detected pH calibration point: {event_info}")
                # More flexible pattern matching for pH measurements
                elif any(phrase in event_info.lower() for phrase in ["ph measurement", "measuring ph", "ph measure"]):
                    current_action = "PRGSample pH measurement"
                    measure_pending = True
                    is_calibration_point = False
                    print(f"📊 Detected pH measurement: {event_info}")
                # More flexible pattern matching for EC measurements  
                elif any(phrase in event_info.lower() for phrase in ["ec measurement", "measuring ec", "ec measure", "conductivity"]):
                    current_action = "PRGSample EC measurement" 
                    measure_pending = True
                    is_calibration_point = False
                    print(f"📊 Detected EC measurement: {event_info}")
                elif "dosing" in event_info.lower():
                    current_action = "Dosing"
                    print(f"💧 Detected dosing action: {event_info}")
                    
                # FIX: Prioritize cycle tracking information
                cycle_match = re.search(r'Starting new PRG(\w+) cycle \((\d+) of (\d+)\)', event_info)
                if cycle_match:
                    prg_type = cycle_match.group(1)
                    current_cycle_num = int(cycle_match.group(2))
                    total_cycles = int(cycle_match.group(3))
                    current_event_type = f"PRG{prg_type}"
                    print(f"👉 Found {current_event_type} cycle #{current_cycle_num} of {total_cycles}")
                
                # FIX: Ensure proper cycle tracking when switching sequences
                elif "Switching to PRGSample sequence" in event_info:
                    current_event_type = "PRGSample"
                    current_cycle_num = 1  # Start at cycle 1 for PRGSample
                    print(f"👉 Detected first PRGSample cycle")
                
                elif "Switching back to PRGCal sequence" in event_info:
                    current_event_type = "PRGCal"
                    current_cycle_num = 1  # FIX: Start at cycle 1 when switching back to PRGCal
                    print(f"👉 Detected return to PRGCal cycle #{current_cycle_num}")
                
                # FIX: Track event numbers separately from cycle numbers
                event_match = re.search(r'PRG(\w+) Event #(\d+) activated', event_info)
                if event_match:
                    prg_type = event_match.group(1)
                    current_event_num = int(event_match.group(2))
                    # FIX: Don't overwrite current_event_type if already set
                    if not current_event_type:
                        current_event_type = f"PRG{prg_type}"
                    print(f"Event: {current_event_type} #{current_event_num} (Cycle: {current_cycle_num})")
                    
                    # Check if this line also contains valid sensor data
                    has_sensor_data = False
                    if len(row) > ph_val_col and row[time_col]:
                        try:
                            if row[ph_val_col] or row[ph_v_col] or row[ec_v_col]:
                                has_sensor_data = True
                        except (ValueError, IndexError):
                            pass

                    # Add event row with no measurements
                    if current_cycle_num is not None and current_event_type is not None:
                        row_timestamp = row[time_col] if time_col < len(row) and row[time_col] else ""
                        extracted_data.append([
                            current_cycle_num,     # Cycle Number
                            current_event_type,    # Event Type
                            current_event_num,     # Event
                            None,                  # Action
                            row_timestamp,         # Time
                            None,                  # Dosing Time (s)
                            None, None,            # EC values
                            None, None,            # pH values
                            None, None             # Nitrate values
                        ])
                        
                        # If there's an action but no sensor data, start looking ahead
                        if current_action and not has_sensor_data and measure_pending:
                            looking_for_data = True
                            look_ahead_count = 0
                            pending_event_data = {
                                'cycle_num': current_cycle_num,
                                'event_type': current_event_type,
                                'event_num': current_event_num,
                                'action': current_action,
                                'dosing_time_s': dosing_time_s
                            }
                            print(f"⏳ Looking ahead for sensor data for {current_action}")
            
            # Process sensor data row
            if len(row) > ph_val_col and row[time_col] and not has_event_info:
                try:
                    # Extrair valores com tratamento para campos vazios
                    time_val = float(row[time_col]) if row[time_col] else 0.0
                    
                    ec_v = float(row[ec_v_col]) if row[ec_v_col] else 0.0
                    ec_ppm = float(row[ec_ppm_col]) if row[ec_ppm_col] else 0.0
                    ph_v = float(row[ph_v_col]) if row[ph_v_col] else 0.0
                    
                    # Tratar casos especiais de pH Value (nan, inf)
                    if row[ph_val_col] and row[ph_val_col].lower() != 'nan' and row[ph_val_col].lower() != 'inf':
                        ph_val = float(row[ph_val_col])
                    else:
                        ph_val = 0.0
                        
                    nitrate_v = float(row[nitrate_v_col]) if row[nitrate_v_col] else 0.0
                    nitrate_ppm = float(row[nitrate_ppm_col]) if row[nitrate_ppm_col] else 0.0

                    # Check if we're looking for data to pair with a previous event
                    if looking_for_data:
                        look_ahead_count += 1
                        
                        # Check if this row has valid sensor data (pH or EC)
                        if ph_val != 0.0 or ph_v != 0.0 or ec_v != 0.0:
                            print(f"✅ Found sensor data {look_ahead_count} rows after event")
                            timestamp = row[time_col]
                            
                            # Add row with sensor data linked to the pending event
                            extracted_data.append([
                                pending_event_data['cycle_num'],     # Cycle Number
                                pending_event_data['event_type'],    # Event Type
                                pending_event_data['event_num'],     # Event
                                pending_event_data['action'],        # Action
                                timestamp,                          # Time (from sensor row)
                                pending_event_data['dosing_time_s'], # Dosing Time (s)
                                ec_v, ec_ppm,                        # EC values
                                ph_v, ph_val,                        # pH values
                                nitrate_v, nitrate_ppm               # Nitrate values
                            ])
                            
                            # Reset look-ahead flags
                            looking_for_data = False
                            pending_event_data = None
                            measure_pending = False
                        
                        # Stop looking if we've reached our limit
                        if look_ahead_count >= look_ahead_limit:
                            print(f"❌ Reached look-ahead limit of {look_ahead_limit} rows without finding sensor data")
                            looking_for_data = False
                            pending_event_data = None
                    
                    # Existing code - only run if not in look-ahead mode
                    elif (measure_pending and current_event_type and current_cycle_num) or (measure_pending and is_calibration_point):
                        if ph_val != 0.0 or ph_v != 0.0:
                            timestamp = row[time_col]
                            
                            extracted_data.append([
                                current_cycle_num,     # Cycle Number
                                current_event_type,    # Event Type
                                current_event_num,     # Event
                                current_action,        # Action
                                timestamp,             # Time
                                dosing_time_s,         # Dosing Time (s)
                                ec_v, ec_ppm,          # EC values
                                ph_v, ph_val,          # pH values
                                nitrate_v, nitrate_ppm # Nitrate values
                            ])
                            
                            # Reset after capturing the measurement
                            measure_pending = False
                            current_action = None
                            dosing_time_s = None
                            
                except (ValueError, IndexError) as e:
                    print(f"Error processing row {row_count}: {e}")
        
    print(f"Processed {row_count} rows")
    print(f"Found {len(extracted_data)} cycle data entries")
    
    if extracted_data:
        with open(output_file, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Simple vertical format - single header row and data rows
            column_names = ['Cycle Number', 'Event Type', 'Event', 'Action', 'Time', 'Dosing Time (s)', 
                           'EC (V)', 'EC (ppm)', 'pH (V)', 'pH Value', 'Nitrate (V)', 'Nitrate (ppm)']
            
            # Write header row once
            writer.writerow(column_names)
            
            # Write all data vertically (one row per measurement)
            for data_row in extracted_data:
                writer.writerow(data_row)
            
        print(f"✅ Successfully wrote cycle data to {output_file}")
    else:
        print("❌ No cycle data found to extract")

def process_all_files(data_dir):
    """Process all sensor_data CSV files in the given directory."""
    pattern = os.path.join(data_dir, "sensor_data_*.csv")
    sensor_files = glob.glob(pattern)
    
    if not sensor_files:
        print(f"No sensor data files found in {data_dir}")
        return
    
    print(f"Found {len(sensor_files)} sensor data files")
    
    for sensor_file in sensor_files:
        base_name = os.path.basename(sensor_file)
        timestamp = base_name.replace("sensor_data_", "").replace(".csv", "")
        output_file = os.path.join(data_dir, f"event_sync_data_{timestamp}.csv")
        
        extract_cycle_data(sensor_file, output_file)

if __name__ == "__main__":
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    
    import sys
    
    print("\n📊 Extract Cycle Data Tool 📊")
    print("1: Select a file with file picker")
    print("2: Process all sensor data files")
    print("3: Exit")
    
    choice = input("Enter your choice (1-3): ")
    
    if choice == "1":
        input_file = show_file_picker(DATA_DIR)
        if input_file:
            input_dir = os.path.dirname(input_file)
            base_name = os.path.basename(input_file)
            output_file = os.path.join(input_dir, base_name.replace("sensor_data", "event_sync_data"))
            extract_cycle_data(input_file, output_file)
        else:
            print("No file selected. Exiting.")
    elif choice == "2":
        process_all_files(DATA_DIR)
    else:
        print("Exiting.")