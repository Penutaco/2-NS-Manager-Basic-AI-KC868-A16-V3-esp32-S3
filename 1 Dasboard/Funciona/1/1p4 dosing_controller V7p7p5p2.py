#!/usr/bin/env python3
"""
AI-Controlled Dosing System for pH and EC Regulation

This PyTorch-based controller manages the dosing of pH and nutrient solutions
in a hydroponic system with precision and intelligence.
"""

import os
import time
import csv
import json
import threading
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from datetime import datetime
import socket
import zmq
import logging
from pathlib import Path
import re
import math
import serial
import traceback

# Configure logging with custom formatter that adds blank lines
class GroupedLogFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.last_timestamp = None
        
    def format(self, record):
        formatted = super().format(record)
        current_timestamp = record.created // 1
        
        # Add blank line before log entry if it's a new second
        if self.last_timestamp is not None and current_timestamp != self.last_timestamp:
            formatted = '\n' + formatted
        
        self.last_timestamp = current_timestamp
        return formatted

# Define formato para facilitar distinção entre grupos de logs
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
formatter = GroupedLogFormatter(log_format)

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.FileHandler("dosing_controller.log"),
        logging.StreamHandler()
    ]
)

# Aplicar o formatter personalizado a todos os handlers
for handler in logging.getLogger().handlers:
    handler.setFormatter(formatter)

logger = logging.getLogger("DosingController")

# System configuration
CONFIG = {
    "tank_volume_liters": 3.0,            # Tank volume in liters
    "target_ph": 6.0,                     # Target pH value (5.5-6.5)
    "target_ec": 500,                     # Target EC value in ppm
    "ph_tolerance": 0.2,                  # Acceptable pH deviation from target
    "ec_tolerance": 50,                   # Acceptable EC deviation from target (±50 ppm)
    "min_dosing_time_ms": 100,            # Atualizado: Tempo mínimo de dosagem em milissegundos (100ms)
    "max_dosing_time_ms": 5000,           # Maximum dosing time in milliseconds
    "safety_factor": 0.5,                 # Conservative factor for dosing (0-1)
    "solution_a_to_b_threshold": 0.8,     # EC depletion rate change threshold for solution switch
    "ph_plus_pin": 27,                    # GPIO pin for pH+ dosing pump (changed from 16)
    "ph_minus_pin": 26,                   # GPIO pin for pH- dosing pump (changed from 17)
    "ec_plus_pin": 25,                    # GPIO pin for EC+ dosing pump (changed from 18)
    "data_dir": os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'),
    "serial_port": "/dev/cu.usbserial-110",  # Porta serial do ESP32
    "serial_baudrate": 115200,               # Baudrate para comunicação serial
    "zmq_timeout_ms": 5000,                  # Timeout para comunicação ZMQ em milissegundos
    "enable_direct_serial": True,            # Flag para habilitar fallback para comunicação serial direta
    
    # NEW CHEMISTRY PARAMETERS
    "ph_minus_molarity": 0.1,                # Molarity of pH- solution (0.1M HCl)
    "ph_plus_molarity": 0.1,                 # Molarity of pH+ solution (0.1M KOH)
    "ec_up_concentration": 200000,           # Nutrient solution concentration in ppm
    "pump_flow_rate": 50.0,                  # Pump flow rate in ml/min
    "chemistry_based_dosing": True,          # Enable chemistry-based calculations
    "learning_rate": 0.2,                    # Rate at which to adjust flow rate based on observed changes
    "adaptive_learning": True,               # Enable adaptive learning from dosing results
    "initial_safety_factor": 0.5,            # Initial 50% safety factor for first dosing
    "flow_calibration_factor": 1.0           # Adjustment factor for pump calibration
}

# Neural network model for dosing predictions
class DosingModel(nn.Module):
    def __init__(self, input_size=8, hidden_size=24, output_size=3):
        super(DosingModel, self).__init__()
        self.network = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, output_size),
            nn.Sigmoid()  # Output between 0-1 (will be scaled to dosing times)
        )
    
    def forward(self, x):
        return self.network(x)

class DosingController:
    def __init__(self, config=CONFIG):
        self.config = config
        self.model = DosingModel()
        self.optimizer = optim.Adam(self.model.parameters(), lr=0.001)
        self.criterion = nn.MSELoss()
        
        # Tracking variables
        self.latest_sensor_data = None
        self.dosing_history = []
        self.ec_depletion_rates = []
        self.current_solution = "A"  # Start with Solution A
        self.running = True
        self.dashboard_socket = None
        self.last_dosing_time = None  # Track last dosing time for cooldown
        
        # Tracking variables for PRG sequence synchronization
        self.last_sample_time = 0       # Timestamp da última medição do PRGSample
        self.sample_detected = False    # Flag que indica que uma nova medição foi detectada
        self.in_prgcal = False          # Flag que indica se PRGCal está em execução
        self.waiting_for_next_sample = False  # Flag de espera pelo próximo ciclo
        
        # Novas variáveis para controle de dosagem por ciclo
        self.last_measurement_id = None
        self.current_measurement_id = None
        self.dosed_in_current_cycle = False
        self.dosing_priority = "EC"  # EC tem prioridade sobre pH
        
        # Chemistry-based dosing tracking variables
        self.dosing_effect_history = []  # Track effectiveness of each dosing
        self.last_ph_before_dosing = None
        self.last_ec_before_dosing = None
        self.dosing_count = {'ph_plus': 0, 'ph_minus': 0, 'ec_plus': 0}  # Count dosing events by type
        
        # Load previous model if exists
        self.model_path = "dosing_model.pth"
        if os.path.exists(self.model_path):
            try:
                self.model.load_state_dict(torch.load(self.model_path))
                logger.info("Loaded existing model")
            except Exception as e:
                logger.error(f"Error loading model: {e}")
        
        # Set up ZMQ communication with dashboard
        self.setup_communication()
        
        # Track the latest data file being written by dashboard
        self.current_data_file = self.find_latest_sensor_file()
        self.last_read_position = 0
        
        logger.info("Dosing controller initialized with chemistry-aware dosing system")

    def setup_communication(self):
        """Set up ZMQ communication with the dashboard"""
        context = zmq.Context()
        self.dashboard_socket = context.socket(zmq.REQ)
        self.dashboard_socket.connect("tcp://localhost:5555")
        logger.info("Connected to dashboard ZMQ socket")

    def find_latest_sensor_file(self):
        """Find the most recent sensor data file in the data directory"""
        try:
            data_files = list(Path(self.config["data_dir"]).glob("sensor_data_*.csv"))
            if not data_files:
                logger.warning("No sensor data files found")
                return None
            
            latest_file = max(data_files, key=lambda p: p.stat().st_mtime)
            logger.info(f"Found latest sensor file: {latest_file}")
            return latest_file
        except Exception as e:
            logger.error(f"Error finding latest sensor file: {e}")
            return None

    def read_latest_sensor_data(self):
        """Read the latest sensor data from the CSV file"""
        # Every 30 seconds, check for new files
        if not hasattr(self, 'last_file_check_time') or time.time() - self.last_file_check_time > 30:
            self.last_file_check_time = time.time()
            if self.check_for_new_files():
                logger.info("Switched to new sensor data file")
        
        # Check for stale data
        if self.check_for_stale_data():
            logger.warning("Stale data detected, forcing file check")
            if self.check_for_new_files():
                logger.info("Found new file after stale data detection")
            else:
                # If no new file but data is stale, reset position to re-read current file
                logger.info("No new file found, resetting read position to check current file")
                self.last_read_position = 0
    
        # Original function code continues here...
        if not self.current_data_file or not os.path.exists(self.current_data_file):
            self.current_data_file = self.find_latest_sensor_file()
            if not self.current_data_file:
                logger.warning("No sensor data file available")
                return None

        try:
            # Check if file has new data
            file_size = os.path.getsize(self.current_data_file)
            if file_size <= self.last_read_position:
                return None  # No new data
            
            # Read only new lines
            with open(self.current_data_file, 'r') as file:
                file.seek(self.last_read_position)
                new_content = file.read()
                self.last_read_position = file.tell()
            
            # Process new lines
            lines = new_content.strip().split('\n')
            valid_lines = []
            
            for line in lines:
                parts = line.split(',')
                # Check if this is a sensor data line with sufficient parts
                if len(parts) >= 11:
                    try:
                        # Extract the relevant sensor data values
                        time_ms = float(parts[0]) if parts[0].strip() else None
                        ec_v = float(parts[4]) if parts[4].strip() else None
                        ec_ppm = float(parts[5]) if parts[5].strip() else None
                        ph_v = float(parts[6]) if parts[6].strip() else None
                        ph_val = float(parts[7]) if parts[7].strip() and parts[7].lower() != 'nan' else None
                        
                        # Validate pH values (0-14 is the valid range)
                        if ph_val is not None and (ph_val < 0 or ph_val > 14):
                            logger.warning(f"INVALID pH READING: {ph_val} - Value outside realistic range (0-14). Dosing skipped.")
                            ph_val = None  # Reset to None to prevent dosing
                        
                        # Validate EC values (typically 0-5000 ppm for hydroponics)
                        if ec_ppm is not None and (ec_ppm < 0 or ec_ppm > 5000):
                            logger.warning(f"INVALID EC READING: {ec_ppm} ppm - Value outside realistic range (0-5000). Dosing skipped.")
                            ec_ppm = None  # Reset to None to prevent dosing
                        
                        # Only include complete readings
                        if all(x is not None for x in [time_ms, ec_v, ec_ppm, ph_v]):
                            valid_lines.append({
                                'time_ms': time_ms,
                                'ec_v': ec_v,
                                'ec_ppm': ec_ppm,
                                'ph_v': ph_v,
                                'ph_val': ph_val
                            })
                    except (ValueError, IndexError) as e:
                        continue  # Skip lines that can't be parsed
            
            if valid_lines:
                self.latest_sensor_data = valid_lines[-1]  # Keep only the most recent reading
                logger.info(f"New sensor data: pH={self.latest_sensor_data['ph_val']}, EC={self.latest_sensor_data['ec_ppm']}")
                return self.latest_sensor_data
                
            return None
        
        except Exception as e:
            logger.error(f"Error reading sensor data: {e}")
            return None

    def process_sensor_data(self):
        # Armazenar apenas valores válidos de pH
        if 'ph_val' in self.latest_sensor_data and self.latest_sensor_data['ph_val'] is not None:
            if not math.isnan(self.latest_sensor_data['ph_val']) and not math.isinf(self.latest_sensor_data['ph_val']):
                self.last_valid_ph = self.latest_sensor_data['ph_val']
        
        # Se o pH atual for inválido mas temos um valor válido anterior, use-o
        if 'ph_val' in self.latest_sensor_data:
            if math.isnan(self.latest_sensor_data['ph_val']) or math.isinf(self.latest_sensor_data['ph_val']):
                if hasattr(self, 'last_valid_ph'):
                    self.latest_sensor_data['ph_val'] = self.last_valid_ph

    def calculate_ec_depletion_rate(self):
        """Calculate the EC depletion rate between readings"""
        if len(self.dosing_history) < 2:
            return None
        
        # Get the last two EC readings where no dosing occurred in between
        recent_readings = [
            entry for entry in self.dosing_history[-10:] 
            if entry['ec_ppm'] is not None and entry['action'] == 'reading'
        ]
        
        if len(recent_readings) < 2:
            return None
        
        # Calculate time difference in seconds and EC difference
        time_diff = (recent_readings[-1]['time_ms'] - recent_readings[-2]['time_ms']) / 1000
        ec_diff = recent_readings[-2]['ec_ppm'] - recent_readings[-1]['ec_ppm']
        
        if time_diff <= 0:
            return None
        
        # EC depletion rate in ppm/hour
        depletion_rate = (ec_diff / time_diff) * 3600
        self.ec_depletion_rates.append(depletion_rate)
        
        # Keep only the most recent 50 depletion rates
        if len(self.ec_depletion_rates) > 50:
            self.ec_depletion_rates = self.ec_depletion_rates[-50:]
        
        return depletion_rate

    def check_solution_transition(self):
        """Check if it's time to transition from Solution A to B based on EC depletion rates"""
        if len(self.ec_depletion_rates) < 10 or self.current_solution != "A":
            return False
        
        # Calculate the slope change in depletion rates
        recent_rates = self.ec_depletion_rates[-10:]
        avg_previous = sum(self.ec_depletion_rates[-20:-10]) / 10 if len(self.ec_depletion_rates) >= 20 else None
        avg_recent = sum(recent_rates) / len(recent_rates)
        
        if avg_previous is None:
            return False
        
        # If depletion rate has significantly increased (plants consuming more nutrients)
        rate_change = avg_recent / avg_previous if avg_previous > 0 else 0
        
        # Check if pH is stable and EC is dropping rapidly
        ph_stable = self.latest_sensor_data and abs(self.latest_sensor_data['ph_val'] - self.config['target_ph']) < 0.3
        
        logger.info(f"EC depletion rate change: {rate_change:.2f}, Threshold: {self.config['solution_a_to_b_threshold']}")
        
        if rate_change > self.config['solution_a_to_b_threshold'] and ph_stable:
            logger.info("Transitioning from Solution A to Solution B")
            self.current_solution = "B"
            return True
        
        return False

    def prepare_model_input(self):
        """Prepare the input tensor for the neural network model"""
        if not self.latest_sensor_data:
            return None
        
        # Create feature vector: [pH, EC, pH-target, EC-target, tank_volume, 
        #                        last_ph_dosing_time, last_ec_dosing_time, solution_type]
        features = [
            self.latest_sensor_data['ph_val'] if self.latest_sensor_data['ph_val'] is not None else self.config['target_ph'],
            self.latest_sensor_data['ec_ppm'],
            abs(self.latest_sensor_data['ph_val'] - self.config['target_ph']) if self.latest_sensor_data['ph_val'] is not None else 0,
            abs(self.latest_sensor_data['ec_ppm'] - self.config['target_ec']),
            self.config['tank_volume_liters'],
            self.get_last_dosing_time('ph_plus') + self.get_last_dosing_time('ph_minus'),
            self.get_last_dosing_time('ec_plus'),
            1.0 if self.current_solution == "B" else 0.0
        ]
        
        return torch.tensor(features, dtype=torch.float32).unsqueeze(0)  # Add batch dimension
    
    def get_last_dosing_time(self, pump_type):
        """Get the last dosing time for a specific pump"""
        for entry in reversed(self.dosing_history):
            if entry['action'] == 'dosing' and entry['pump'] == pump_type:
                return entry['dosing_time_ms']
        return 0

    def predict_dosing_times(self):
        """Use the model to predict optimal dosing times"""
        model_input = self.prepare_model_input()
        if model_input is None:
            return None, None, None
        
        # Get model predictions (0-1 range for each pump)
        with torch.no_grad():
            predictions = self.model(model_input).squeeze().tolist()
        
        # Scale predictions to actual dosing times
        min_time = self.config['min_dosing_time_ms']
        max_time = self.config['max_dosing_time_ms']
        safety = self.config['safety_factor']
        
        ph_plus_time = int(predictions[0] * (max_time - min_time) * safety + min_time) if predictions[0] > 0.1 else 0
        ph_minus_time = int(predictions[1] * (max_time - min_time) * safety + min_time) if predictions[1] > 0.1 else 0
        ec_plus_time = int(predictions[2] * (max_time - min_time) * safety + min_time) if predictions[2] > 0.1 else 0
        
        # Ensure we're not activating conflicting pumps (pH+ and pH-)
        if ph_plus_time > 0 and ph_minus_time > 0:
            if predictions[0] > predictions[1]:
                ph_minus_time = 0
            else:
                ph_plus_time = 0
        
        return ph_plus_time, ph_minus_time, ec_plus_time

    def calculate_chemical_dosing_volume(self, pump_type):
        """Calculate required dosing volume based on chemical principles"""
        if not self.latest_sensor_data:
            logger.warning("No sensor data available for chemical calculations")
            return None, 0
            
        ph_val = self.latest_sensor_data.get('ph_val')
        ec_ppm = self.latest_sensor_data.get('ec_ppm')
        
        # Validations
        if ph_val is None or ec_ppm is None:
            logger.warning(f"Incomplete sensor data for chemical calculations: pH={ph_val}, EC={ec_ppm}")
            return None, 0
            
        tank_volume_ml = self.config['tank_volume_liters'] * 1000  # Convert L to mL
        
        # Calculate dosing volume based on chemical type
        if pump_type == "ph_plus":
            # pH+ calculation (logarithmic)
            current_h_conc = 10**(-ph_val)  # Convert pH to [H+]
            target_h_conc = 10**(-self.config['target_ph'])  # Target [H+]
            
            # Calculate mmol of OH- needed to neutralize excess H+
            mmol_oh_needed = (current_h_conc - target_h_conc) * tank_volume_ml / 1000
            
            # CORRECTED LOGIC
            # Positive value means we need to add OH- (pH+)
            if mmol_oh_needed > 0:  # CHANGED from < 0 to > 0
                mmol_oh_needed = abs(mmol_oh_needed)
                
                # Calculate mL needed from pH+ solution
                solution_molarity = self.config['ph_plus_molarity']
                ml_needed = mmol_oh_needed / solution_molarity
                
                logger.info(f"Chemical calculation: {mmol_oh_needed:.4f} mmol OH- needed, {ml_needed:.2f} mL of {solution_molarity}M pH+ solution")
                return "ph_plus", ml_needed
            else:
                logger.info("pH already at or above target, no pH+ needed")
                return None, 0
                
        elif pump_type == "ph_minus":
            # pH- calculation (logarithmic)
            current_h_conc = 10**(-ph_val)  # Convert pH to [H+]
            target_h_conc = 10**(-self.config['target_ph'])  # Target [H+]
            
            # Calculate mmol of H+ needed to reach target pH
            mmol_h_needed = (target_h_conc - current_h_conc) * tank_volume_ml / 1000
            
            # Positive value means we need to add H+ (pH-)
            if mmol_h_needed > 0:
                # Calculate mL needed from pH- solution
                solution_molarity = self.config['ph_minus_molarity']  # mol/L
                ml_needed = mmol_h_needed / solution_molarity
                
                logger.info(f"Chemical calculation: {mmol_h_needed:.4f} mmol H+ needed, {ml_needed:.2f} mL of {solution_molarity}M pH- solution")
                return "ph_minus", ml_needed
            else:
                logger.info("pH already at or below target, no pH- needed")
                return None, 0
                
        elif pump_type == "ec_plus":
            # EC+ calculation (linear dilution)
            ec_difference = self.config['target_ec'] - ec_ppm
            
            if ec_difference > 0:
                # Using dilution formula: C₁V₁ = C₂V₂
                # C₁ = nutrient concentration, V₁ = volume to add
                # C₂ = target increase in EC, V₂ = tank volume
                
                nutrient_concentration = self.config['ec_up_concentration']  # ppm
                ml_needed = (ec_difference * tank_volume_ml) / nutrient_concentration
                
                logger.info(f"Chemical calculation: {ec_difference} ppm EC increase needed, {ml_needed:.2f} mL of {nutrient_concentration} ppm nutrient solution")
                return "ec_plus", ml_needed
            else:
                logger.info("EC already at or above target, no EC+ needed")
                return None, 0
        
        return None, 0
        
    def convert_volume_to_dosing_time(self, volume_ml):
        """Convert required volume to pump activation time"""
        if volume_ml <= 0:
            return 0
            
        # Convert volume (mL) to time (ms) based on pump flow rate
        # flow_rate is in mL/min, so convert to mL/ms
        flow_rate_ml_per_ms = self.config['pump_flow_rate'] / (60 * 1000)
        
        # Apply calibration factor from learning
        calibrated_flow_rate = flow_rate_ml_per_ms * self.config.get('flow_calibration_factor', 1.0)
        
        # Calculate dosing time
        dosing_time_ms = int(volume_ml / calibrated_flow_rate)
        
        # Apply safety limits
        dosing_time_ms = min(dosing_time_ms, self.config['max_dosing_time_ms'])
        dosing_time_ms = max(dosing_time_ms, self.config['min_dosing_time_ms'])
        
        logger.info(f"Volume {volume_ml:.2f} mL converted to dosing time {dosing_time_ms} ms (flow rate: {self.config['pump_flow_rate']:.1f} mL/min)")
        return dosing_time_ms
        
    def apply_adaptive_learning(self, pump_type, volume_dosed, before_value, after_value):
        """Learn from the actual effect of dosing and adapt future calculations"""
        if not self.config.get('adaptive_learning', True):
            return
            
        # Skip if either value is None
        if before_value is None or after_value is None:
            logger.warning("Cannot apply learning: missing before/after values")
            return
            
        observed_change = abs(after_value - before_value)
        
        if observed_change == 0:
            logger.info("No change observed from dosing, cannot update model")
            return
            
        # Store the effect of this dosing for learning
        if pump_type.startswith("ph"):
            # For pH pumps, store how much pH changed per mL
            effect_per_ml = observed_change / volume_dosed
            
            # Update our understanding of solution strength
            key = 'ph_plus_molarity' if pump_type == "ph_plus" else 'ph_minus_molarity'
            current_value = self.config.get(key, 0.1)
            
            # Update using learning rate
            learning_rate = self.config.get('learning_rate', 0.2)
            new_value = current_value * (1 - learning_rate) + (effect_per_ml * learning_rate)
            
            # Store back in config
            self.config[key] = new_value
            logger.info(f"Updated {key} from {current_value:.4f} to {new_value:.4f} based on observed effect")
            
        elif pump_type == "ec_plus":
            # For EC pump, store how much EC changed per mL
            effect_per_ml = observed_change / volume_dosed
            
            # Update our understanding of EC solution strength
            current_value = self.config.get('ec_up_concentration', 200000)
            
            # Update using learning rate
            learning_rate = self.config.get('learning_rate', 0.2)
            new_value = current_value * (1 - learning_rate) + (effect_per_ml * tank_volume_ml * learning_rate)
            
            # Store back in config
            self.config['ec_up_concentration'] = new_value
            logger.info(f"Updated EC solution concentration from {current_value:.0f} to {new_value:.0f} ppm based on observed effect")
        
    def chemistry_based_dosing_decision(self, measurement_type):
        """Make dosing decisions based on chemical calculations rather than heuristics"""
        if not self.config.get('chemistry_based_dosing', True):
            # Fall back to original method if chemistry-based dosing is disabled
            return self.should_dose_with_priority(measurement_type)
            
        if not self.latest_sensor_data:
            logger.warning("No sensor data available for chemistry-based dosing decision")
            return None
            
        ph_val = self.latest_sensor_data.get('ph_val')
        ec_ppm = self.latest_sensor_data.get('ec_ppm')
        
        # Validations
        if ph_val is None or ec_ppm is None:
            logger.warning(f"Incomplete sensor data: pH={ph_val}, EC={ec_ppm}")
            return None
            
        # Check deviations
        ph_deviation = abs(ph_val - self.config['target_ph'])
        ec_deviation = abs(ec_ppm - self.config['target_ec'])
        
        logger.info(f"Chemistry analysis - pH: {ph_val:.2f} (deviation: {ph_deviation:.2f}), EC: {ec_ppm:.0f} (deviation: {ec_deviation:.0f})")
        
        # First priority: Check if EC needs correction
        if ec_deviation > self.config['ec_tolerance']:
            if ec_ppm < self.config['target_ec']:
                # EC is low, calculate volume needed for EC+
                _, volume_needed = self.calculate_chemical_dosing_volume("ec_plus")
                
                # Apply safety factor for first few dosings
                if len([e for e in self.dosing_history if e.get('pump') == 'ec_plus']) < 5:
                    safety_factor = self.config.get('initial_safety_factor', 0.5)
                    volume_needed *= safety_factor
                    logger.info(f"Applying safety factor {safety_factor} to EC+ dosing: {volume_needed:.2f} mL")
                
                # Convert to dosing time
                dosing_time = self.convert_volume_to_dosing_time(volume_needed)
                
                if dosing_time >= self.config['min_dosing_time_ms']:
                    logger.info(f"Chemistry decision: Increase EC with {volume_needed:.2f} mL ({dosing_time} ms)")
                    return "ec_plus", dosing_time
        
        # Second priority: Check if pH needs correction
        if ph_deviation > self.config['ph_tolerance']:
            # Determine which pH adjustment is needed
            if ph_val < self.config['target_ph']:
                # pH is low, calculate volume needed for pH+
                _, volume_needed = self.calculate_chemical_dosing_volume("ph_plus")
                
                # Apply safety factor for first few dosings
                if len([e for e in self.dosing_history if e.get('pump') == 'ph_plus']) < 5:
                    safety_factor = self.config.get('initial_safety_factor', 0.5)
                    volume_needed *= safety_factor
                    logger.info(f"Applying safety factor {safety_factor} to pH+ dosing: {volume_needed:.2f} mL")
                
                # Convert to dosing time
                dosing_time = self.convert_volume_to_dosing_time(volume_needed)
                
                if dosing_time >= self.config['min_dosing_time_ms']:
                    logger.info(f"Chemistry decision: Increase pH with {volume_needed:.2f} mL ({dosing_time} ms)")
                    return "ph_plus", dosing_time
                    
            else:
                # pH is high, calculate volume needed for pH-
                _, volume_needed = self.calculate_chemical_dosing_volume("ph_minus")
                
                # Apply safety factor for first few dosings
                if len([e for e in self.dosing_history if e.get('pump') == 'ph_minus']) < 5:
                    safety_factor = self.config.get('initial_safety_factor', 0.5)
                    volume_needed *= safety_factor
                    logger.info(f"Applying safety factor {safety_factor} to pH- dosing: {volume_needed:.2f} mL")
                
                # Convert to dosing time
                dosing_time = self.convert_volume_to_dosing_time(volume_needed)
                
                if dosing_time >= self.config['min_dosing_time_ms']:
                    logger.info(f"Chemistry decision: Decrease pH with {volume_needed:.2f} mL ({dosing_time} ms)")
                    return "ph_minus", dosing_time
        
        logger.info("Chemistry decision: No dosing needed, parameters within tolerance")
        return None

    def determine_dosing_action(self):
        """Determine which dosing action to take based on sensor readings"""
        if not self.latest_sensor_data or self.latest_sensor_data['ph_val'] is None:
            return None, 0
        
        # If we have minimal historical data, start with conservative empirical approach
        if len(self.dosing_history) < 10:
            return self.empirical_dosing()
        
        # Otherwise use the machine learning model for prediction
        return self.ml_based_dosing()
    
    def empirical_dosing(self):
        """Use a conservative empirical approach for initial dosing"""
        ph_val = self.latest_sensor_data['ph_val']
        ec_ppm = self.latest_sensor_data['ec_ppm']
        
        # Add validation checks
        if ph_val is None:
            logger.warning("Cannot dose: pH reading is invalid or missing")
            return None, 0
            
        if ec_ppm is None:
            logger.warning("Cannot dose: EC reading is invalid or missing")
            return None, 0
        
        # Log current values vs targets
        logger.info(f"Current pH: {ph_val:.2f}, Target: {self.config['target_ph']:.2f}, Deviation: {abs(ph_val - self.config['target_ph']):.2f}")
        logger.info(f"Current EC: {ec_ppm:.0f} ppm, Target: {self.config['target_ec']:.0f} ppm, Deviation: {abs(ec_ppm - self.config['target_ec']):.0f} ppm")
        
        # Determine which value needs correction more urgently
        ph_deviation = abs(ph_val - self.config['target_ph'])
        ec_deviation_ppm = abs(ec_ppm - self.config['target_ec'])
        
        # Calculate relative deviations (what percent of tolerance are we off by?)
        ph_relative_deviation = ph_deviation / self.config['ph_tolerance']
        ec_relative_deviation = ec_deviation_ppm / self.config['ec_tolerance']
        
        # Log debug information
        logger.info(f"DEBUG: ph_deviation={ph_deviation}, ph_tolerance={self.config['ph_tolerance']}, ph_relative={ph_relative_deviation:.2f}")
        logger.info(f"DEBUG: ec_deviation={ec_deviation_ppm}, ec_tolerance={self.config['ec_tolerance']}, ec_relative={ec_relative_deviation:.2f}")
        
        # Start with minimum dosing times
        min_time = self.config['min_dosing_time_ms']
        
        # 1. Check if pH is outside tolerance
        if ph_deviation > self.config['ph_tolerance']:
            # 2. Check if EC is outside tolerance
            if ec_deviation_ppm > self.config['ec_tolerance']:
                # Both are outside tolerance - choose the one that's more urgent
                if ph_relative_deviation > ec_relative_deviation:
                    # pH needs correction more urgently
                    if ph_val < self.config['target_ph']:
                        logger.info(f"DOSING: pH+ to raise pH from {ph_val:.2f} toward target {self.config['target_ph']:.2f}")
                        return "ph_plus", min_time
                    else:
                        logger.info(f"DOSING: pH- to lower pH from {ph_val:.2f} toward target {self.config['target_ph']:.2f}")
                        return "ph_minus", min_time
                else:
                    # EC needs correction more urgently
                    if ec_ppm < self.config['target_ec']:
                        logger.info(f"DOSING: EC+ to increase EC from {ec_ppm:.0f} ppm toward target {self.config['target_ec']:.0f} ppm")
                        return "ec_plus", min_time
            else:
                # Only pH is outside tolerance
                if ph_val < self.config['target_ph']:
                    logger.info(f"DOSING: pH+ to raise pH from {ph_val:.2f} toward target {self.config['target_ph']:.2f}")
                    return "ph_plus", min_time
                else:
                    logger.info(f"DOSING: pH- to lower pH from {ph_val:.2f} toward target {self.config['target_ph']:.2f}")
                    return "ph_minus", min_time
        elif ec_deviation_ppm > self.config['ec_tolerance']:
            # Only EC is outside tolerance
            if ec_ppm < self.config['target_ec']:
                logger.info(f"DOSING: EC+ to increase EC from {ec_ppm:.0f} ppm toward target {self.config['target_ec']:.0f} ppm")
                return "ec_plus", min_time
        
        logger.info("No dosing needed: values within tolerance")
        return None, 0
    
    def ml_based_dosing(self):
        """Use the machine learning model to determine dosing action"""
        ph_plus_time, ph_minus_time, ec_plus_time = self.predict_dosing_times()
        
        # Determine the most needed correction
        ph_val = self.latest_sensor_data['ph_val']
        ec_ppm = self.latest_sensor_data['ec_ppm']
        
        # Add validation checks
        if ph_val is None or ec_ppm is None:
            logger.warning("Cannot perform ML-based dosing: invalid sensor readings")
            return None, 0
        
        ph_deviation = abs(ph_val - self.config['target_ph'])
        
        # Direct comparison using ppm values
        ec_deviation = abs(ec_ppm - self.config['target_ec']) / self.config['target_ec']
        
        # Only dose if we're outside tolerance
        if ph_deviation <= self.config['ph_tolerance'] and ec_deviation <= self.config['ec_tolerance']:
            return None, 0
            
        # Select the most appropriate pump based on deviations and predicted times
        if ph_deviation > self.config['ph_tolerance'] and ph_deviation > ec_deviation:
            if ph_val < self.config['target_ph'] and ph_plus_time > 0:
                logger.info(f"ML DOSING: pH+ to raise pH from {ph_val:.2f} toward target {self.config['target_ph']:.2f}")
                return "ph_plus", ph_plus_time
            elif ph_val > self.config['target_ph'] and ph_minus_time > 0:
                logger.info(f"ML DOSING: pH- to lower pH from {ph_val:.2f} toward target {self.config['target_ph']:.2f}")
                return "ph_minus", ph_minus_time
        
        if ec_deviation > self.config['ec_tolerance'] and ec_ppm < self.config['target_ec'] and ec_plus_time > 0:
            logger.info(f"ML DOSING: EC+ to increase EC from {ec_ppm:.0f} ppm toward target {self.config['target_ec']:.0f} ppm")
            return "ec_plus", ec_plus_time
            
        return None, 0

    def should_dose_with_priority(self, measurement_type):
        """Decide se deve dosar com base na prioridade (EC > pH)"""
        if not self.latest_sensor_data:
            logger.warning("Sem dados de sensores para decidir dosagem")
            return None
        
        ph_val = self.latest_sensor_data.get('ph_val')
        ec_ppm = self.latest_sensor_data.get('ec_ppm')
        
        # Validação de dados
        if ph_val is None or ec_ppm is None:
            logger.warning(f"Dados de sensores incompletos: pH={ph_val}, EC={ec_ppm}")
            return None
        
        # Cálculo de desvios
        ph_deviation = abs(ph_val - self.config['target_ph'])
        ec_deviation = abs(ec_ppm - self.config['target_ec'])
        
        # Verifica se EC está fora do intervalo aceitável
        ec_needs_correction = ec_deviation > self.config['ec_tolerance']
        
        # Verifica se pH está fora do intervalo aceitável
        ph_needs_correction = ph_deviation > self.config['ph_tolerance']
        
        logger.info(f"Análise de desvios: EC={ec_ppm} (desvio: {ec_deviation}, limite: {self.config['ec_tolerance']}), " +
                    f"pH={ph_val} (desvio: {ph_deviation}, limite: {self.config['ph_tolerance']})")
        
        # Configurações para dosagem
        max_dosing_time = self.config['max_dosing_time_ms']
        min_dosing_time = self.config['min_dosing_time_ms']
        
        # MODIFICADO: Agora sempre avalia tanto pH quanto EC, mas mantém a prioridade
        # LÓGICA DE PRIORIDADE: Primeiro corrigir EC, depois pH
        if ec_needs_correction:
            # Corrige EC se EC precisar correção
            if ec_ppm < self.config['target_ec']:
                max_deviation = 1000
                normalized_deviation = min(ec_deviation, max_deviation) / max_deviation
                dosing_time = int(min_dosing_time + normalized_deviation * (max_dosing_time - min_dosing_time))
                logger.info(f"Decisão: Aumentar EC (prioridade) - desvio: {ec_deviation} ppm, tempo: {dosing_time}ms")
                return "ec_plus", dosing_time
                
        elif ph_needs_correction:
            # Corrige pH somente se EC já estiver ok
            max_deviation = 2.0
            normalized_deviation = min(ph_deviation, max_deviation) / max_deviation
            dosing_time = int(min_dosing_time + normalized_deviation * (max_dosing_time - min_dosing_time))
            
            if ph_val < self.config['target_ph']:
                logger.info(f"Decisão: Aumentar pH - desvio: {ph_deviation}, tempo: {dosing_time}ms")
                return "ph_plus", dosing_time
            else:
                logger.info(f"Decisão: Diminuir pH - desvio: {ph_deviation}, tempo: {dosing_time}ms")
                return "ph_minus", dosing_time
        
        logger.info("Decisão: Nenhuma dosagem necessária com a prioridade atual")
        return None

    def send_dosing_command(self, pump_type, dosing_time_ms):
        """Send a dosing command to the ESP32 via ZMQ or direct serial connection"""
        # Determine pin to activate based on pump type
        pin = None
        if pump_type == "ph_plus":
            pin = self.config["ph_plus_pin"]
        elif pump_type == "ph_minus":
            pin = self.config["ph_minus_pin"]
        elif pump_type == "ec_plus":
            pin = self.config["ec_plus_pin"]
        else:
            logger.error(f"Unknown pump type: {pump_type}")
            return False
        
        # Create command message
        command = {
            "action": "dose",
            "pin": pin,
            "duration_ms": dosing_time_ms,
            "pump_type": pump_type
        }
        
        # First attempt: ZMQ communication
        success = False
        communication_method = "ZMQ"
        
        try:
            if self.dashboard_socket:
                logger.info(f"Attempting ZMQ communication for {pump_type} dosing ({dosing_time_ms} ms)")
                
                # Set timeout for ZMQ socket
                self.dashboard_socket.setsockopt(zmq.RCVTIMEO, self.config["zmq_timeout_ms"])
                
                # Send command to dashboard
                self.dashboard_socket.send_json(command)
                
                # Wait for response with timeout
                start_time = time.time()
                response = self.dashboard_socket.recv_json()
                elapsed_ms = (time.time() - start_time) * 1000
                
                logger.info(f"ZMQ response received in {elapsed_ms:.0f}ms: {response}")
                
                success = response.get('success', False)
                if success:
                    logger.info(f"ZMQ dosing successful: {pump_type} for {dosing_time_ms}ms on pin {pin}")
                else:
                    logger.warning(f"ZMQ dosing command failed: {response}")
            else:
                logger.warning("ZMQ socket not available, skipping ZMQ attempt")
                
        except zmq.error.Again:
            logger.warning(f"ZMQ communication timed out after {self.config['zmq_timeout_ms']}ms")
        except Exception as e:
            logger.error(f"ZMQ communication error: {e}")
            logger.debug(traceback.format_exc())
        
        # Second attempt: Direct serial communication (if ZMQ failed and direct serial is enabled)
        if not success and self.config["enable_direct_serial"]:
            communication_method = "DIRECT_SERIAL"
            try:
                logger.info(f"Attempting direct serial communication for {pump_type} dosing ({dosing_time_ms} ms)")
                
                # Format the JSON command exactly as expected by the ESP32
                cmd = json.dumps(command) + '\n'
                
                with serial.Serial(self.config["serial_port"], self.config["serial_baudrate"], timeout=1) as ser:
                    # Clear any pending data
                    ser.reset_input_buffer()
                    
                    # Send the command
                    ser.write(cmd.encode())
                    
                    # Wait for response
                    start_time = time.time()
                    response_received = False
                    response_text = ""
                    
                    # Read for up to 2 seconds for confirmation
                    while time.time() - start_time < 2.0:
                        if ser.in_waiting:
                            line = ser.readline().decode().strip()
                            response_text += line + " | "
                            
                            # Look for success indicators in the response
                            if "activated" in line.lower() or "success" in line.lower():
                                response_received = True
                                success = True
                            
                            # Look for error indicators
                            if "error" in line.lower() or "invalid" in line.lower():
                                response_received = True
                                success = False
                        
                        time.sleep(0.1)
                    
                    if success:
                        logger.info(f"Direct serial dosing successful: {pump_type} for {dosing_time_ms}ms on pin {pin}")
                    else:
                        logger.warning(f"Direct serial dosing failed or timed out. Response: {response_text}")
                    
            except Exception as e:
                logger.error(f"Direct serial communication error: {e}")
                logger.debug(traceback.format_exc())
        
        # Log the action with communication method used
        if success:
            self.dosing_history.append({
                'time_ms': self.latest_sensor_data['time_ms'],
                'ph_val': self.latest_sensor_data['ph_val'],
                'ec_ppm': self.latest_sensor_data['ec_ppm'],
                'action': 'dosing',
                'pump': pump_type,
                'dosing_time_ms': dosing_time_ms,
                'communication': communication_method
            })
            
            # Update last dosing time for cooldown
            self.last_dosing_time = time.time()
        
        return success

    def dosing_cooldown_active(self):
        """Dummy method that always returns False since cooldown is disabled"""
        return False

    def get_cooldown_remaining(self):
        """Dummy method that always returns 0 since cooldown is disabled"""
        return 0

    def train_model(self):
        """Train the model on historical dosing data"""
        if len(self.dosing_history) < 20:
            return  # Not enough data for training
        
        # Create training dataset from dosing history
        train_features = []
        train_labels = []
        
        for i in range(len(self.dosing_history) - 1):
            entry = self.dosing_history[i]
            next_entry = self.dosing_history[i + 1]
            
            # Skip entries without proper data
            if (entry['action'] != 'dosing' or 
                entry['ph_val'] is None or 
                next_entry['ph_val'] is None):
                continue
            
            # Calculate effect of dosing
            ph_change = next_entry['ph_val'] - entry['ph_val']
            ec_change = next_entry['ec_ppm'] - entry['ec_ppm']
            
            # Create feature vector
            feature = [
                entry['ph_val'],
                entry['ec_ppm'],
                abs(entry['ph_val'] - self.config['target_ph']),
                abs(entry['ec_ppm'] - self.config['target_ec']),
                self.config['tank_volume_liters'],
                self.get_last_dosing_time('ph_plus', i),
                self.get_last_dosing_time('ph_minus', i),
                1.0 if self.current_solution == "B" else 0.0
            ]
            
            # Create label vector (normalized dosing times)
            max_time = self.config['max_dosing_time_ms']
            min_time = self.config['min_dosing_time_ms']
            range_time = max_time - min_time
            
            if entry['pump'] == 'ph_plus':
                label = [entry['dosing_time_ms'] / range_time, 0, 0]
            elif entry['pump'] == 'ph_minus':
                label = [0, entry['dosing_time_ms'] / range_time, 0]
            elif entry['pump'] == 'ec_plus':
                label = [0, 0, entry['dosing_time_ms'] / range_time]
            else:
                continue
            
            train_features.append(feature)
            train_labels.append(label)
        
        if not train_features:
            return  # No valid training data
        
        # Convert to PyTorch tensors
        X = torch.tensor(train_features, dtype=torch.float32)
        y = torch.tensor(train_labels, dtype=torch.float32)
        
        # Train for a few epochs
        self.model.train()
        for epoch in range(5):
            self.optimizer.zero_grad()
            outputs = self.model(X)
            loss = self.criterion(outputs, y)
            loss.backward()
            self.optimizer.step()
        
        # Save updated model
        torch.save(self.model.state_dict(), self.model_path)
        logger.info(f"Model trained on {len(train_features)} samples, loss: {loss.item():.6f}")
    
    def get_last_dosing_time(self, pump_type, index=None):
        """Get the last dosing time for a specific pump before a given history index"""
        history = self.dosing_history if index is None else self.dosing_history[:index]
        
        for entry in reversed(history):
            if entry.get('action') == 'dosing' and entry.get('pump') == pump_type:
                return entry.get('dosing_time_ms', 0)
        return 0

    def append_to_csv(self, pump_type, dosing_time_ms):
        """Append dosing events to the CSV files in addition to what dashboard already logs"""
        # Find the current CSV files
        if not self.current_data_file:
            self.current_data_file = self.find_latest_sensor_file()
            if not self.current_data_file:
                logger.warning("No sensor data file available for logging")
                return
        
        # Get the corresponding event file
        event_file_path = str(self.current_data_file).replace('sensor_data_', 'extracted_cycle_data_')
        if not os.path.exists(event_file_path):
            logger.warning(f"Event file not found: {event_file_path}")
            return
        
        try:
            # Read existing CSV to determine new column index
            with open(event_file_path, 'r', newline='') as csvfile:
                reader = csv.reader(csvfile)
                header = next(reader)
                
                # Add new columns if they don't exist
                new_columns = ["Pump Type", "Dosing Time (ms)", "Timestamp"]
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                
                # Create row with empty values except for our new data
                row = [""] * len(header)
                row.extend([pump_type, str(dosing_time_ms), current_time])
                
                # Append the new row
                with open(event_file_path, 'a', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(row)
                
                logger.info(f"Dosing event logged to CSV: {pump_type}, {dosing_time_ms}ms")
        except Exception as e:
            logger.error(f"Error appending to CSV: {e}")

    def detect_prg_events(self):
        """Detect only PRGCal events, ignoring PRGSample events (simplified)"""
        if not self.current_data_file:
            return False
            
        # Usa diretamente o arquivo sensor_data.csv para buscar eventos
        event_file_path = self.current_data_file
        if not os.path.exists(event_file_path):
            return False
            
        try:
            # Lê o arquivo CSV de dados dos sensores
            with open(event_file_path, 'r') as file:
                file_size = os.path.getsize(event_file_path)
                if file_size > 10000:
                    file.seek(max(0, file_size - 10000))
                    file.readline()
                    
                lines = file.readlines()
                
                # Na primeira linha, encontra o índice da coluna "Event Info"
                header = lines[0].strip().split(',')
                event_info_idx = -1
                for i, col_name in enumerate(header):
                    if "Event" in col_name and "Info" in col_name:
                        event_info_idx = i
                        break
                        
                if event_info_idx == -1:
                    event_info_idx = len(header) - 1
                    logger.warning(f"Column 'Event Info' not found in header, using last column ({event_info_idx}) as fallback")
                
                # Procura SOMENTE por eventos PRGCal
                for line in reversed(lines[-30:]):
                    parts = line.strip().split(',')
                    if len(parts) <= event_info_idx:
                        continue
                        
                    event_info = parts[event_info_idx]
                    if not event_info:
                        continue
                    
                    # SOMENTE detecta mudanças de status de PRGCal
                    if "PRGCal" in event_info:
                        if "Starting new PRGCal" in event_info:
                            if not self.in_prgcal:
                                logger.info("PRGCal sequence detected - pausing dosing")
                                self.in_prgcal = True
                                return True
                        elif "PRGCal sequence complete" in event_info:
                            if self.in_prgcal:
                                logger.info("PRGCal sequence completed - resuming dosing")
                                self.in_prgcal = False
                                return True
                
                return False
        except Exception as e:
            logger.error(f"Error detecting PRG events: {e}")
            return False

    def detect_prgsample_measurement(self):
        """Detecta especificamente os eventos PRGSample Event #2 da serial do ESP32"""
        if not self.current_data_file or self.in_prgcal:
            return None
            
        # Usa diretamente o arquivo sensor_data.csv
        event_file_path = self.current_data_file
        
        try:
            # Lê o arquivo CSV de dados dos sensores
            with open(event_file_path, 'r') as file:
                # Lê apenas as últimas partes se for um arquivo grande
                file_size = os.path.getsize(event_file_path)
                if file_size > 10000:
                    file.seek(max(0, file_size - 10000))
                    file.readline()  # Descarta primeira linha incompleta
                    
                lines = file.readlines()
                
                # Na primeira linha, encontra o índice da coluna "Event Info"
                header = lines[0].strip().split(',')
                event_info_idx = -1
                for i, col_name in enumerate(header):
                    if "Event" in col_name and "Info" in col_name:
                        event_info_idx = i
                        break
                        
                if event_info_idx == -1:
                    event_info_idx = len(header) - 1
                    logger.warning(f"Column 'Event Info' not found in header, using last column ({event_info_idx}) as fallback")
                
                # Procura APENAS pelo evento específico "PRGSample Event #2"
                for i, line in enumerate(reversed(lines[-100:])):  # Verifica as últimas 100 linhas
                    parts = line.strip().split(',')
                    if len(parts) <= event_info_idx:
                        continue
                        
                    event_info = parts[event_info_idx]
                    if not event_info:
                        continue
                    
                    # MODIFICAÇÃO: Detecta APENAS o evento "PRGSample Event #2"
                    if "PRGSample Event #2" in event_info:
                        # Extrai número do ciclo, ou usa timestamp como fallback
                        cycle_match = re.search(r"cycle \((\d+) of", event_info)
                        cycle_id = int(cycle_match.group(1)) if cycle_match else int(time.time())
                        logger.info(f"DETECÇÃO: Evento PRGSample Event #2 encontrado - Ciclo: {cycle_id}")
                        return "pH", cycle_id  # Mantém "pH" como tipo para compatibilidade
                
                # Nenhum evento "PRGSample Event #2" foi encontrado
                return None
                
        except Exception as e:
            logger.error(f"Error detecting PRGSample Event #2: {e}")
            logger.debug(traceback.format_exc())
            return None

    def detect_from_dashboard_logs(self):
        """Detecta medições do PRGSample nos logs do dashboard"""
        if not self.current_data_file:
            return False
        
        # Busca pelo arquivo de log correspondente
        log_file_path = str(self.current_data_file).replace('sensor_data_', 'extracted_cycle_data_')
        if not os.path.exists(log_file_path):
            return False

        try:
            # Verifica o timestamp do arquivo para não reler o mesmo arquivo constantemente
            file_mtime = os.path.getmtime(log_file_path)
            
            # Se já verificamos este arquivo recentemente, pulamos
            if hasattr(self, 'last_file_check_time') and self.last_file_check_time == file_mtime:
                return False
            
            # Atualiza timestamp de verificação
            self.last_file_check_time = file_mtime
            
            # Lê o arquivo inteiro para garantir que encontremos todos os eventos
            with open(log_file_path, 'r') as file:
                content = file.read()
                
                # Verifica se contém medições PRGSample recentes
                if "PRGSample pH measurement" in content or "PRGSample EC measurement" in content:
                    # Obtém a hora atual
                    current_time = time.time()
                    
                    # Se a última medição foi há mais de 10 segundos, considera nova
                    if current_time - self.last_sample_time > 10:
                        self.last_sample_time = current_time
                        logger.info(f"DETECÇÃO: Medição do PRGSample encontrada nos logs")
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Erro ao ler logs do dashboard: {e}")
            return False

    def detect_from_esp32_serial(self):
        """Detecta medições do PRGSample via comunicação serial com ESP32"""
        try:
            with serial.Serial(self.config["serial_port"], self.config["serial_baudrate"], timeout=0.1) as ser:
                # Limpa buffer
                ser.reset_input_buffer()
                
                # Formato correto do comando com todos os campos necessários
                command = {
                    "action": "status_query",
                    "timestamp": time.time(),
                    "request_id": str(int(time.time() * 1000))  # ID único para o comando
                }
                
                # Envia comando para verificar status
                ser.write((json.dumps(command) + '\n').encode())
                
                # Espera por resposta por um curto período
                start_time = time.time()
                while time.time() - start_time < 0.5:
                    if ser.in_waiting:
                        line = ser.readline().decode().strip()
                        logger.debug(f"Serial response: {line}")
                        
                        # Verifica se a resposta indica uma medição recente
                        if "PRGSample" in line and "measurement" in line:
                            current_time = time.time()
                            
                            # Se a última medição foi há mais de 10 segundos, considera nova
                            if current_time - self.last_sample_time > 10:
                                self.last_sample_time = current_time
                                logger.info(f"DETECÇÃO: Medição do PRGSample detectada via comunicação serial")
                                return True
                    
                    time.sleep(0.05)
            
            return False
        
        except Exception as e:
            logger.debug(f"Erro na comunicação serial (isso é esperado se ESP32 não estiver conectado): {e}")
            return False

    def log_system_status(self):
        """Log detailed system status for diagnostics"""
        if not self.latest_sensor_data:
            logger.info("System Status: No sensor data available")
            return

        # Format current values vs targets with clear visual indicators
        ph_current = self.latest_sensor_data.get('ph_val')
        ec_current = self.latest_sensor_data.get('ec_ppm')
        
        if ph_current is not None:
            ph_diff = ph_current - self.config['target_ph']
            ph_status = "🟢" if abs(ph_diff) <= self.config['ph_tolerance'] else "🔴"
            ph_direction = "↑" if ph_diff < 0 else "↓" if ph_diff > 0 else "="
            logger.info(f"pH Status: {ph_status} Current: {ph_current:.2f} | Target: {self.config['target_ph']:.2f} | Diff: {ph_diff:.2f} {ph_direction}")
        else:
            logger.info("pH Status: ⚠️ No valid reading")
            
        if ec_current is not None:
            ec_diff = ec_current - self.config['target_ec']
            ec_status = "🟢" if abs(ec_diff) <= self.config['ec_tolerance'] else "🔴"
            ec_direction = "↑" if ec_diff < 0 else "↓" if ec_diff > 0 else "="
            logger.info(f"EC Status: {ec_status} Current: {ec_current:.0f} | Target: {self.config['target_ec']} | Diff: {ec_diff:.0f} {ec_direction}")
        else:
            logger.info("EC Status: ⚠️ No valid reading")
        
        # Log PRGSample cycle information from dashboard log
        cycle_info = self.get_current_prgsample_cycle()
        if cycle_info:
            logger.info(f"PRGSample Cycle: {cycle_info['current']} of {cycle_info['total']} (Last event: {cycle_info['last_event']})")
        else:
            logger.info("PRGSample Cycle: Not detected")
        
        logger.info(f"PRG Status: {'In PRGCal' if self.in_prgcal else 'Normal'} | Waiting for sample: {self.waiting_for_next_sample}")
        logger.info(f"Dosing Status: Ready")

    def get_current_prgsample_cycle(self):
        """Extract current PRGSample cycle information from sensor_data.csv Event Info column"""
        if not self.current_data_file:
            logger.debug("No current data file available for cycle detection")
            return None
            
        # Usa diretamente o arquivo sensor_data.csv
        event_file_path = self.current_data_file
        
        if not os.path.exists(event_file_path):
            logger.debug(f"Sensor data file not found: {event_file_path}")
            return None
                
        try:
            # Log para depuração
            logger.debug(f"Checking PRGSample cycle in: {event_file_path}")
            
            # Lê o arquivo CSV
            with open(event_file_path, 'r') as file:
                lines = file.readlines()
                
                # Na primeira linha, encontra o índice da coluna "Event Info"
                header = lines[0].strip().split(',')
                event_info_idx = -1
                for i, col_name in enumerate(header):
                    # Busca mais flexível para encontrar a coluna Event Info
                    if "Event" in col_name and "Info" in col_name:
                        event_info_idx = i
                        logger.debug(f"Found Event Info column at index {i}: '{col_name}'")
                        break
                        
                if event_info_idx == -1:
                    # Tentar último índice como fallback (geralmente a última coluna)
                    event_info_idx = len(header) - 1
                    logger.info(f"Using last column ({event_info_idx}) as Event Info column")
                
                # Resto do método permanece igual...
                
                # Variáveis para armazenar o ciclo mais recente
                current_cycle = None
                total_cycles = None
                last_event = None
                
                # Procura por ciclo PRGSample nas linhas (da mais recente para a mais antiga)
                for line in reversed(lines[1:]):  # Pula o cabeçalho
                    parts = line.strip().split(',')
                    if len(parts) <= event_info_idx:
                        continue
                        
                    event_info = parts[event_info_idx]
                    if not event_info:
                        continue
                    
                    # Procura pelo padrão "Starting new PRGSample cycle (X of Y)"
                    if "Starting new PRGSample cycle" in event_info:
                        cycle_match = re.search(r"\((\d+) of (\d+)\)", event_info)
                        if cycle_match:
                            current_cycle = int(cycle_match.group(1))
                            total_cycles = int(cycle_match.group(2))
                            logger.debug(f"Found cycle: {current_cycle} of {total_cycles}")
                            break  # Encontramos o ciclo mais recente, podemos parar
                
                # Procura pelo evento PRGSample mais recente
                for line in reversed(lines[1:]):  # Pula o cabeçalho
                    parts = line.strip().split(',')
                    if len(parts) <= event_info_idx:
                        continue
                        
                    event_info = parts[event_info_idx]
                    if not event_info:
                        continue
                    
                    event_match = re.search(r"PRGSample Event #(\d+)", event_info)
                    if event_match:
                        last_event = f"Event #{event_match.group(1)}"
                        logger.debug(f"Found event: {last_event}")
                        break  # Encontramos o evento mais recente, podemos parar
                
                # Se encontramos um ciclo, retornamos as informações
                if current_cycle is not None and total_cycles is not None:
                    cycle_info = {
                        'current': current_cycle,
                        'total': total_cycles,
                        'last_event': last_event if last_event else "Unknown"
                    }
                    logger.info(f"Found PRGSample cycle {current_cycle} of {total_cycles} in sensor data file")
                    return cycle_info
                
                # Se chegou aqui, não encontrou ciclo
                logger.debug("No PRGSample cycle found in sensor data file")
                return None
                
        except Exception as e:
            logger.error(f"Error detecting PRGSample cycle: {e}")
            logger.debug(traceback.format_exc())
            return None

    def manual_dose(self, pump_type, dosing_time_ms):
        """Manual dosing command for testing and calibration"""
        logger.info(f"MANUAL DOSING: {pump_type} for {dosing_time_ms}ms")
        
        # Validate pump type
        if pump_type not in ["ph_plus", "ph_minus", "ec_plus"]:
            logger.error(f"Invalid pump type: {pump_type}")
            return False
        
        # Validate dosing time
        if not isinstance(dosing_time_ms, int) or dosing_time_ms <= 0:
            logger.error(f"Invalid dosing time: {dosing_time_ms}")
            return False
        
        # Execute the dosing command
        success = self.send_dosing_command(pump_type, dosing_time_ms)
        
        if success:
            logger.info(f"MANUAL DOSING SUCCESS: {pump_type} for {dosing_time_ms}ms")
            
            # Log the manual dosing event
            if self.latest_sensor_data:
                self.dosing_history.append({
                    'time_ms': self.latest_sensor_data.get('time_ms', time.time() * 1000),
                    'ph_val': self.latest_sensor_data.get('ph_val'),
                    'ec_ppm': self.latest_sensor_data.get('ec_ppm'),
                    'action': 'manual_dosing',
                    'pump': pump_type,
                    'dosing_time_ms': dosing_time_ms
                })
                
                # Log to CSV
                self.append_to_csv(pump_type, dosing_time_ms)
        else:
            logger.error(f"MANUAL DOSING FAILED: {pump_type} for {dosing_time_ms}ms")
            
        return success

    def check_for_new_files(self):
        """Periodically check if new data files have been created"""
        latest_file = self.find_latest_sensor_file()
        
        if latest_file and latest_file != self.current_data_file:
            logger.info(f"Detected new data file: {latest_file}")
            logger.info(f"Switching from: {self.current_data_file}")
            self.current_data_file = latest_file
            self.last_read_position = 0  # Reset read position for new file
            return True
        return False

    def check_for_stale_data(self):
        """Check if we're seeing the same data values for too long"""
        if not hasattr(self, 'last_sensor_values'):
            self.last_sensor_values = None
            self.stale_data_count = 0
            self.last_data_change_time = time.time()
            return False
        
        if self.latest_sensor_data:
            current_values = (
                self.latest_sensor_data.get('ph_val'),
                self.latest_sensor_data.get('ec_ppm')
            )
            
            if self.last_sensor_values == current_values:
                self.stale_data_count += 1
                # If data hasn't changed for 5 minutes (300 seconds)
                if time.time() - self.last_data_change_time > 300:
                    logger.warning(f"Data values unchanged for 5 minutes. Possible stale file.")
                    return True
            else:
                self.last_sensor_values = current_values
                self.stale_data_count = 0
                self.last_data_change_time = time.time()
                
        return False

    def run(self):
        """Loop principal com nova lógica de detecção e dosagem por ciclo"""
        while self.running:
            try:
                # Lê dados mais recentes dos sensores
                new_data = self.read_latest_sensor_data()
                
                # Add file checking as a failsafe if no data received for some time
                if not new_data and not hasattr(self, 'last_successful_read'):
                    self.last_successful_read = time.time()
                elif not new_data and time.time() - self.last_successful_read > 60:  # 1 minute with no data
                    logger.warning("No new data received for 60 seconds, checking for new files...")
                    self.check_for_new_files()
                    self.last_successful_read = time.time()
                elif new_data:
                    self.last_successful_read = time.time()
                
                if new_data:
                    # Record pre-dosing values for learning
                    pre_dosing_ph = new_data.get('ph_val')
                    pre_dosing_ec = new_data.get('ec_ppm')
                    
                    # Processa os dados
                    self.process_sensor_data()
                    
                    # Registra leitura
                    self.dosing_history.append({
                        'time_ms': new_data['time_ms'],
                        'ph_val': new_data['ph_val'],
                        'ec_ppm': new_data['ec_ppm'],
                        'action': 'reading'
                    })
                    
                    # Log status atual
                    self.log_system_status()
                    
                    # Verifica eventos PRGCal (isso ainda precisa ser verificado para evitar dosagem durante calibração)
                    self.detect_prg_events()
                    
                    # NOVA LÓGICA: Detecta especificamente o tipo de medição
                    measurement_result = self.detect_prgsample_measurement()
                    
                    # Se detectou uma medição e NÃO está em calibração
                    if measurement_result and not self.in_prgcal:
                        measurement_type, cycle_id = measurement_result  # ← Unpack the tuple
                        
                        # Gerar um ID único para esta medição baseado no timestamp
                        self.current_measurement_id = int(time.time())
                        
                        # Verifica se é uma nova medição comparando com a anterior
                        if self.current_measurement_id != self.last_measurement_id:
                            logger.info(f"NOVO CICLO: Medição de {measurement_type} detectada - ID: {self.current_measurement_id}")
                            self.dosed_in_current_cycle = False  # Reinicia flag de dosagem para o novo ciclo
                            self.last_measurement_id = self.current_measurement_id
                        
                        # Só realiza dosagem se ainda não dosou neste ciclo
                        if not self.dosed_in_current_cycle:
                            # MODIFIED: Use chemistry-based dosing instead of priority-based dosing
                            should_dose = self.chemistry_based_dosing_decision(measurement_type) if self.config.get('chemistry_based_dosing', True) else self.should_dose_with_priority(measurement_type)
                            
                            if should_dose:
                                pump_type, dosing_time = should_dose
                                
                                # Garante dose mínima de 25ms
                                if dosing_time < 25:
                                    dosing_time = 25
                                    
                                logger.info(f"DOSIFICAÇÃO: Ativando bomba {pump_type} por {dosing_time}ms para {measurement_type}")
                                success = self.send_dosing_command(pump_type, dosing_time)
                                
                                if success:
                                    # Store the volume dosed for learning
                                    flow_rate_ml_per_ms = self.config['pump_flow_rate'] / (60 * 1000)
                                    volume_dosed = dosing_time * flow_rate_ml_per_ms
                                    
                                    logger.info(f"SUCESSO: Dosificação de {pump_type} concluída - Volume: {volume_dosed:.2f} mL")
                                    self.dosed_in_current_cycle = True  # Marca que já dosou neste ciclo
                                    self.append_to_csv(pump_type, dosing_time)
                                    
                                    # Wait for some time to allow system to stabilize
                                    time.sleep(5)
                                    
                                    # Read new sensor data to see effect of dosing
                                    after_data = self.read_latest_sensor_data()
                                    if after_data:
                                        # Apply adaptive learning
                                        if pump_type.startswith("ph"):
                                            self.apply_adaptive_learning(pump_type, volume_dosed, pre_dosing_ph, after_data.get('ph_val'))
                                        elif pump_type == "ec_plus":
                                            self.apply_adaptive_learning(pump_type, volume_dosed, pre_dosing_ec, after_data.get('ec_ppm'))
                                else:
                                    logger.error(f"FALHA: Dosificação de {pump_type} falhou")
                            else:
                                logger.info(f"NENHUMA DOSAGEM NECESSÁRIA para {measurement_type} neste ciclo")
                
                # Breve pausa para evitar uso excessivo da CPU
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Erro no loop de controle: {e}")
                logger.debug(traceback.format_exc())
                time.sleep(5)  # Pausa maior em caso de erro

    def stop(self):
        """Stop the control loop cleanly"""
        self.running = False

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='AI-Controlled Dosing System')
    parser.add_argument('--dose', choices=['ph_plus', 'ph_minus', 'ec_plus'], 
                        help='Manually trigger specific pump for testing')
    parser.add_argument('--time', type=int, default=1000, 
                        help='Dosing time in milliseconds for manual dosing')
    args = parser.parse_args()
    
    try:
        controller = DosingController()
        
        # Handle manual dosing command if specified
        if args.dose:
            controller.read_latest_sensor_data()  # Get latest sensor data first
            success = controller.manual_dose(args.dose, args.time)
            print(f"Manual dosing {'successful' if success else 'failed'}")
            exit(0)
        
        # Normal operation - start controller thread
        controller_thread = threading.Thread(target=controller.run)
        controller_thread.start()
        
        print("Dosing controller started. Press Ctrl+C to stop.")
        
        # Wait for keyboard interrupt
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down dosing controller...")
        if 'controller' in locals():
            controller.stop()