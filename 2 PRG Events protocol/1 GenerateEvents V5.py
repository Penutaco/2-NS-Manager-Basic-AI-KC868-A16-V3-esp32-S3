import csv
import os
import tkinter as tk
import re
from tkinter.filedialog import askopenfilename

# Initialize Tkinter and hide the main window
root = tk.Tk()
root.withdraw()

print("Opening file selection dialog...")

# Open a file dialog to select the CSV file
csv_filename = askopenfilename(
    title="Select LED Schedule CSV",
    filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
)

if not csv_filename:
    print("No file selected. Exiting.")
    exit(1)

print(f"Selected file: {csv_filename}")

# Define the output header filename based on the input CSV filename
header_filename = os.path.splitext(csv_filename)[0] + ".h"

# Store the rows we need
rows_to_process = []

with open(csv_filename, newline='') as csvfile:
    reader = csv.reader(csvfile)
    
    # Check if the first row is a comment (starts with '//')
    first_row = next(reader, None)
    if first_row and len(first_row) > 2 and str(first_row[2]).startswith("//"):
        print("Skipping comment row:", first_row)
        header_row = next(reader, None)
    else:
        header_row = first_row

    # Store all valid rows, skipping rows where the time value (column C, index 2) is not an integer
    for row in reader:
        if not row or len(row) < 3 or not row[2].strip():
            print(f"Skipping empty or short row: {row}")
            continue
            
        try:
            # Try converting the third column (C, index 2) to int; if fails, skip the row
            int(row[2])
            rows_to_process.append(row)
        except ValueError:
            # Skip rows where the time value is not a valid integer
            print(f"Skipping row with non-integer time value: {row}")
            continue
            
        # Check for END marker
        if row[2].strip().upper() == "END":
            print("Found END marker, stopping processing")
            break

    print(f"Found {len(rows_to_process)} valid rows to process")

    # Process the rows to create events
    events = []
    for row in rows_to_process:
        # Extract values starting from column C (index 2)
        time_val = int(row[2])              # Column C: Time
        ref = int(row[3])                   # Column D: Reference Flag
        measure = int(row[4])               # Column E: Measure Flag
        ec_sensor = float(row[5])           # Column F: EC Sensor Calibration Value
        ph_sensor = float(row[6])           # Column G: pH Sensor Calibration Value
        nitrate_sensor = float(row[7])      # Column H: Nitrate Sensor Calibration Value
        
        # Process GPIO values (starting from column I, index 8)
        led_state = 0
        gpio_values = row[8:]  # Get GPIO values from column I onwards
        
        for i, gpio_value in enumerate(gpio_values):
            if gpio_value.strip() == "1":
                led_state |= (1 << i)
        
        events.append((time_val, ref, measure, ph_sensor, nitrate_sensor, ec_sensor, led_state))
        print(f"Added event: time={time_val}, ref={ref}, measure={measure}, EC={ec_sensor}, pH={ph_sensor}, Nitrate={nitrate_sensor}, LED state={led_state}")

# Generate header file
with open(header_filename, "w") as header_file:
    basename = os.path.splitext(os.path.basename(csv_filename))[0]
    # Sanitize guardname by replacing spaces and special characters with underscores
    guardname = re.sub(r'[^A-Za-z0-9_]', '_', basename.upper())
    
    # Ensure consistent case for array and constant names
    if basename.lower().startswith("prgcal"):
        arrayname = "PRGcalEvents"
        numEventsName = "numPRGcalEvents"
    elif basename.lower().startswith("prgsample"):
        arrayname = "PRGsampleEvents"
        numEventsName = "numPRGsampleEvents"
    else:
        arrayname = basename + "Events"
        numEventsName = "num" + basename + "Events"

    # Write header with proper includes and declarations
    header_file.write(f"""// Generated events file. Do not edit manually.
#ifndef {guardname}_H
#define {guardname}_H

#include "Event.h"

// Define the number of events for this sequence
const int {numEventsName} = {len(events)};  // Number of events

// Define the event sequence
Event {arrayname}[{numEventsName}] = {{
""")
    
    # Write events array with proper formatting
    for event in events:
        time_val, ref, measure, ph_sensor, nitrate_sensor, ec_sensor, led_state = event
        header_file.write(
            f"    {{{time_val}, {ref}, {measure}, {led_state}, {ph_sensor}, {nitrate_sensor}, {ec_sensor}}}, "
            f" // time={time_val}, REF={ref}, Measure={measure}, LEDs={led_state}, pH={ph_sensor}, Nitrate={nitrate_sensor}, EC={ec_sensor}\n"
        )
    
    header_file.write("};\n\n")
    header_file.write(f"#endif // {guardname}_H\n")

print(f"Generated {header_filename} with {len(events)} events")
print("NOTE: This version skips columns A and B, allowing you to use them for comments.")