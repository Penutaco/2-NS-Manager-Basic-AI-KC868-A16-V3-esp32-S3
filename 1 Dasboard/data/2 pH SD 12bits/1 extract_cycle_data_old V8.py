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
    
    # Track state
    current_event_type = None
    current_cycle_num = None
    current_event_num = None
    measure_pending = False
    is_calibration_point = False  # Nova flag para pontos de calibração
    
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
        
        row_count = 0
        for row in reader:
            row_count += 1
            
            # Skip empty rows
            if not row or len(row) < 2:
                continue
            
            # Determine if this is a data row or event row
            has_event_info = False
            if len(row) >= 11 and row[10]:  # Check if Event Info column has data
                # This has event info - process it
                event_info = row[10]
                has_event_info = True
                
                if debug_mode and row_count < 100:  # Print first 100 rows only
                    print(f"Event info found: {event_info}")
                
                # Check for cycle information
                cycle_match = re.search(r'Starting new PRG(\w+) cycle \((\d+) of (\d+)\)', event_info)
                if cycle_match:
                    prg_type = cycle_match.group(1)
                    current_cycle_num = int(cycle_match.group(2))
                    total_cycles = int(cycle_match.group(3))
                    current_event_type = f"PRG{prg_type}"
                    print(f"👉 Found {current_event_type} cycle #{current_cycle_num} of {total_cycles}")
                
                # Detectar quando há troca para a sequência PRGSample (primeiro ciclo)
                elif "Switching to PRGSample sequence" in event_info:
                    current_event_type = "PRGSample"
                    current_cycle_num = 1
                    print(f"👉 Detected first PRGSample cycle")
                
                # Detectar quando há troca de volta para a sequência PRGCal
                elif "Switching back to PRGCal sequence" in event_info:
                    current_event_type = "PRGCal"
                    current_cycle_num = 2  # Assumindo que este é o segundo ciclo do PRGCal
                    print(f"👉 Detected return to PRGCal cycle #{current_cycle_num}")
                
                # Check for event number
                event_match = re.search(r'PRG(\w+) Event #(\d+) activated', event_info)
                if event_match:
                    prg_type = event_match.group(1)
                    current_event_num = int(event_match.group(2))
                    current_event_type = f"PRG{prg_type}"
                    print(f"Event: {current_event_type} #{current_event_num}")
                
                # Look for DEBUG message with measureValue=1
                if "DEBUG: Event #" in event_info and "measureValue=1" in event_info:
                    measure_pending = True
                    print(f"🔍 Detected measure=1 event: {event_info}")
                
                # Check if this line records a pH calibration point or measurement
                if "Recorded pH calibration point" in event_info:
                    measure_pending = True
                    is_calibration_point = True  # Marca como ponto de calibração
                    print(f"📊 Detected pH calibration point: {event_info}")
                elif "PRGSample pH measurement" in event_info:
                    measure_pending = True
                    print(f"📊 Detected sensor measurement: {event_info}")
                
                # Check if this is one of the known measure=1 events in PRGCal/PRGSample
                if current_event_type == "PRGCal" and current_event_num in [4, 9]:  # From PRGCal.h
                    measure_pending = True
                    print(f"📊 Detected known measure=1 event: {current_event_type} #{current_event_num}")
                
                elif current_event_type == "PRGSample" and current_event_num == 3:  # From PRGSample.h
                    measure_pending = True
                    print(f"📊 Detected known measure=1 event: {current_event_type} #{current_event_num}")
            
            # Process sensor data if this is a data row with numeric values
            if len(row) >= 9 and row[0] and not has_event_info:  # Has timestamp and numeric data
                try:
                    # Try to convert values - if this fails, it's not a data row
                    time_val = float(row[0]) if row[0] else 0.0
                    
                    # Extract the sensor values we need based on your CSV structure
                    ec_v = float(row[4]) if row[4] else 0.0    # EC Voltage
                    ec_ppm = float(row[5]) if row[5] else 0.0  # EC PPM
                    ph_v = float(row[6]) if row[6] else 0.0    # pH Voltage
                    ph_val = float(row[7]) if row[7] and row[7].lower() != 'nan' and row[7].lower() != 'inf' else 0.0  # pH Value
                    nitrate_v = float(row[8]) if row[8] else 0.0    # Nitrate Voltage
                    nitrate_ppm = 0.0  # Not present in this CSV
                    
                    # If we're waiting for sensor data after a measure=1 event, capture it
                    if (measure_pending and current_event_type and current_cycle_num) or (measure_pending and is_calibration_point):
                        # Check if pH Value is valid (not nan or inf)
                        if ph_val != 0.0 or ph_v != 0.0:
                            # Record this measurement
                            timestamp = row[0]  # Use Time column from input file
                            
                            # Para pontos de calibração sem ciclo, use valores padrão
                            if is_calibration_point and not (current_event_type and current_cycle_num):
                                event_type = "PRGCal"
                                cycle_num = 1  # Modificado de "Cal" para 1 (primeiro ciclo)
                            else:
                                event_type = current_event_type
                                cycle_num = current_cycle_num
                                
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
                            
                            # Reset the pending flags after capturing data
                            measure_pending = False
                            is_calibration_point = False  # Resetar a flag
                except (ValueError, IndexError) as e:
                    if debug_mode:
                        print(f"⚠️ Error processing row {row_count}: {e}")
        
    print(f"Processed {row_count} rows")
    print(f"Found {len(extracted_data)} cycle data entries")
    
    # Write the extracted data to the output file
    if extracted_data:
        with open(output_file, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Organizar os dados por fases de execução (PRGCal -> conjunto PRGSample -> PRGCal -> conjunto PRGSample)
            phases = []
            current_phase = []
            current_type = None
            
            # Identificar as fases de execução
            for i, row in enumerate(extracted_data):
                event_type = row[0]
                cycle_num = row[1]
                
                # Detectar transições entre PRGCal e PRGSample
                if event_type != current_type:
                    if current_phase:
                        phases.append(current_phase)
                        current_phase = []
                    current_type = event_type
                
                current_phase.append(row)
                
                # Se este é o último registro, adicionar a fase atual
                if i == len(extracted_data) - 1:
                    phases.append(current_phase)
            
            # Verificar se temos fases suficientes e estruturar os dados
            # Formato esperado: [PRGCal_1, PRGSample_set1, PRGCal_2, PRGSample_set2]
            data_blocks = []
            
            # Separar os dados em blocos conforme o arquivo de exemplo
            for i, phase in enumerate(phases):
                if i < 4:  # Limita a 4 blocos como no exemplo
                    data_blocks.append(phase)
            
            # Garantir que temos pelo menos espaços vazios para todos os blocos
            while len(data_blocks) < 4:
                data_blocks.append([])
            
            # Criar o cabeçalho
            column_names = ['Event Type', 'Cycle Number', 'Time', 'EC (V)', 'EC (ppm)', 
                           'pH (V)', 'pH Value', 'Nitrate (V)', 'Nitrate (ppm)']
            header_row = []
            
            # Duplicar o cabeçalho para cada bloco
            for _ in range(4):
                header_row.extend(column_names)
            
            writer.writerow(header_row)
            
            # Encontrar o número máximo de linhas em qualquer bloco
            max_rows = max([len(block) for block in data_blocks]) if data_blocks else 0
            
            # Escrever os dados em formato de grade
            for row_idx in range(max_rows):
                output_row = []
                
                # Para cada bloco, adicionar dados ou colunas vazias
                for block in data_blocks:
                    if row_idx < len(block):
                        output_row.extend(block[row_idx])
                    else:
                        output_row.extend([''] * len(column_names))
                
                writer.writerow(output_row)
            
        print(f"✅ Successfully wrote cycle data to {output_file}")
    else:
        print("❌ No cycle data found to extract")

def process_all_files(data_dir):
    """Process all sensor_data CSV files in the given directory."""
    # Find all sensor_data CSV files
    pattern = os.path.join(data_dir, "sensor_data_*.csv")
    sensor_files = glob.glob(pattern)
    
    if not sensor_files:
        print(f"No sensor data files found in {data_dir}")
        return
    
    print(f"Found {len(sensor_files)} sensor data files")
    
    for sensor_file in sensor_files:
        # Generate output filename
        base_name = os.path.basename(sensor_file)
        timestamp = base_name.replace("sensor_data_", "").replace(".csv", "")
        output_file = os.path.join(data_dir, f"extracted_cycle_data_{timestamp}.csv")
        
        # Process the file
        extract_cycle_data(sensor_file, output_file)

# Main execution block - this is what was missing
if __name__ == "__main__":
    # Define the data directory (same as in dashboard)
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    
    import sys
    
    # Add a simple text interface to choose operation mode
    print("\n📊 Extract Cycle Data Tool 📊")
    print("1: Select a file with file picker")
    print("2: Process all sensor data files")
    print("3: Exit")
    
    choice = input("Enter your choice (1-3): ")
    
    if choice == "1":
        input_file = show_file_picker(DATA_DIR)
        if input_file:
            # Generate output filename in same directory as input file
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