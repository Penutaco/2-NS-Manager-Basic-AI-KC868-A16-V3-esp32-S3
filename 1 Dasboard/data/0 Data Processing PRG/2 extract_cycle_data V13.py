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
    
    # Store extracted data
    extracted_data = []
    
    # Debug
    debug_mode = True  # Set to True to see detailed output
    
    with open(input_file, 'r', newline='') as csvfile:
        reader = csv.reader(csvfile)
        headers = next(reader)  # Skip header row
        
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
            
            # Skip empty rows
            if not row or len(row) < 2:
                continue
            
            # Determine if this is a data row or event row
            has_event_info = False
            if len(row) > event_info_col and row[event_info_col]:  # Check if Event Info column has data
                # This has event info - process it
                event_info = row[event_info_col]
                has_event_info = True
                
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
                
                # Sempre iniciar como não sendo ponto de calibração
                is_calibration_point = False
                
                # Adaptar regex para novos formatos de calibração e medição
                if "PRGCal pH calibration point" in event_info:
                    measure_pending = True
                    is_calibration_point = True
                    print(f"📊 Detected pH calibration point: {event_info}")
                elif "PRGSample pH measurement" in event_info:
                    measure_pending = True
                    is_calibration_point = False  # Explicitamente não é calibração
                    print(f"📊 Detected sensor measurement: {event_info}")
                # Método antigo - manter apenas para PRGSample evento 3
                elif current_event_type == "PRGSample" and current_event_num == 3:
                    measure_pending = True
                    is_calibration_point = False  # Explicitamente não é calibração
                    print(f"📊 Detected known measure=1 event: {current_event_type} #{current_event_num}")
            
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

                    # FIX: Ensure we use cycle_num consistently when storing data
                    if (measure_pending and current_event_type and current_cycle_num) or (measure_pending and is_calibration_point):
                        if ph_val != 0.0 or ph_v != 0.0:
                            timestamp = row[time_col]
                            
                            if is_calibration_point and not (current_event_type and current_cycle_num):
                                event_type = "PRGCal"
                                cycle_num = 1
                            else:
                                event_type = current_event_type
                                cycle_num = current_cycle_num  # Use the cycle number, not event number
                                
                            extracted_data.append([
                                event_type,
                                cycle_num,
                                timestamp,
                                ec_v, ec_ppm,
                                ph_v, ph_val,
                                nitrate_v, nitrate_ppm
                            ])
                            
                            print(f"✅ Found sensor data for {event_type} cycle {cycle_num}")
                            print(f"   EC: {ec_v}V / {ec_ppm}ppm, pH: {ph_v}V / {ph_val}")
                            
                            measure_pending = False
                            is_calibration_point = False
                except (ValueError, IndexError) as e:
                    if debug_mode:
                        print(f"⚠️ Error processing row {row_count}: {e}")
        
    print(f"Processed {row_count} rows")
    print(f"Found {len(extracted_data)} cycle data entries")
    
    if extracted_data:
        with open(output_file, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Simple vertical format - single header row and data rows
            column_names = ['Event Type', 'Cycle Number', 'Time', 'EC (V)', 'EC (ppm)', 
                           'pH (V)', 'pH Value', 'Nitrate (V)', 'Nitrate (ppm)']
            
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
        output_file = os.path.join(data_dir, f"extracted_cycle_data_{timestamp}.csv")
        
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
            output_file = os.path.join(input_dir, base_name.replace("sensor_data", "extracted_cycle_data"))
            extract_cycle_data(input_file, output_file)
        else:
            print("No file selected. Exiting.")
    elif choice == "2":
        process_all_files(DATA_DIR)
    else:
        print("Exiting.")