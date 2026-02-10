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
import collections
import uuid

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
    "target_ec": 1.0,                     # Target EC in mS/cm (changed from 0.2)
    "ph_tolerance": 0.2,                  # Acceptable pH deviation from target
    "ec_tolerance": 0.1,                  # Acceptable EC deviation in mS/cm (changed from 50 ppm)
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
    "ec_up_volume_per_ec": 2.5,              # mL of EC+ solution per L of tank volume per 1.0 mS/cm increase
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
        
        # New titration coefficient tracking variables
        self.ph_plus_titration_coefficient = self.config.get('ph_plus_molarity', 0.1)
        self.ph_minus_titration_coefficient = self.config.get('ph_minus_molarity', 0.1)
        self.ec_specific_conductivity_coefficient = self.config.get('ec_up_volume_per_ec', 2.5)
        
        # Cycle tracking for learning
        self.last_cycle_id = None
        self.current_cycle_id = None
        self.last_cycle_ph_value = None
        self.last_cycle_ec_value = None
        self.last_cycle_dosing = None  # Stores information about the last dosing
        
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
        
        # Rastreador de eventos processados
        self.processed_events = {}  # Format: {cycle_id: timestamp}
        
        # Adicionar rastreador de eventos por ID único 
        self.event_unique_ids = {}  # Format: {event_id: {'cycle_id': cycle_id, 'timestamp': timestamp}}
        
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
        # Instead of one pointer, use separate pointers:
        self.last_ph_read_position = 0
        self.last_event_read_position = 0

        self.current_event_file = self.find_latest_event_file()
        # Inicializa o ponteiro dedicado para leitura do arquivo de eventos
        self.last_event_read_position = 0
        
        # Adicionar buffer circular para eventos
        self.event_buffer = collections.deque(maxlen=50)  # Armazena até 50 eventos
        self.event_buffer_window_seconds = 60  # Janela de tempo para considerar eventos no buffer (60 segundos)
        
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

    def find_latest_event_file(self):
        """Find the most recent event data file in the data directory"""
        try:
            event_files = list(Path(self.config["data_dir"]).glob("event_data_*.csv"))
            if not event_files:
                logger.warning("No event data files found")
                return None
            latest_file = max(event_files, key=lambda p: p.stat().st_mtime)
            logger.info(f"Found latest event file: {latest_file}")
            return latest_file
        except Exception as e:
            logger.error(f"Error finding latest event file: {e}")
            return None

    def check_for_new_files(self):
        """Check for new sensor data files and switch if needed."""
        try:
            new_file = self.find_latest_sensor_file()
            if new_file and (str(new_file) != str(self.current_data_file)):
                logger.info(f"New file detected: {new_file}. Switching from {self.current_data_file}")
                self.current_data_file = new_file
                # Reset all file pointers
                self.last_read_position = 0
                self.last_ph_read_position = 0
                self.last_event_read_position = 0
                return True
            return False
        except Exception as e:
            logger.error(f"Error checking for new files: {e}")
            return False

    def check_for_stale_data(self):
        """Check if the current sensor data is stale based on timestamp."""
        try:
            if self.latest_sensor_data and 'time_ms' in self.latest_sensor_data:
                last_time = self.latest_sensor_data['time_ms']
                current_time = time.time() * 1000  # current time in ms
                # Consider data stale if older than 60 seconds
                if current_time - last_time > 60000:
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking for stale data: {e}")
            return False

    def read_latest_sensor_data(self):
        """Read the latest sensor data from the CSV file"""
        # Esta função está desativada pois estamos lendo dados apenas do event_data.csv
        logger.debug("read_latest_sensor_data() está desativado - usando apenas event_data.csv")
        return None

    def process_next_line_sensor_data(self, line):
        """Process sensor data from the line following the PRGSample pH measurement event"""
        try:
            parts = line.strip().split(',')
            if len(parts) >= 8:  # Check if we have enough columns
                time_ms = float(parts[0]) if parts[0].strip() else None
                ec_v = float(parts[4]) if parts[4].strip() else None
                ec_mScm = float(parts[5]) if parts[5].strip() else None
                ph_v = float(parts[6]) if parts[6].strip() else None
                ph_val = float(parts[7]) if parts[7].strip() and parts[7].lower() != 'nan' else None
                
                # Basic validation
                if ph_val is not None and (ph_val < 0 or ph_val > 14):
                    logger.warning(f"INVALID pH READING: {ph_val} - Value outside realistic range (0-14).")
                    ph_val = None
                    
                if ec_mScm is not None and (ec_mScm < 0 or ec_mScm > 5):
                    logger.warning(f"INVALID EC READING: {ec_mScm} mS/cm - Value outside realistic range (0-5).")
                    ec_mScm = None
                
                # Store the data
                if all(x is not None for x in [time_ms, ec_v, ec_mScm, ph_v, ph_val]):
                    self.latest_sensor_data = {
                        'time_ms': time_ms,
                        'ec_v': ec_v,
                        'ec_mScm': ec_mScm,
                        'ph_v': ph_v,
                        'ph_val': ph_val
                    }
                    logger.info(f"Sensor data processed: pH={ph_val:.2f}, EC={ec_mScm:.2f} mS/cm")
        except Exception as e:
            logger.error(f"Error processing data line: {e}")

    def detect_prgsample_ph_measurement(self):
        """
        Detect PRGSample pH measurement events in the event_data file.
        Returns a tuple of (measurement_type, cycle_id) if detected, else None.
        """
        if not self.current_event_file:
            self.current_event_file = self.find_latest_event_file()
            if not self.current_event_file:
                return None

        try:
            with open(self.current_event_file, 'r') as file:
                # Salvar posição ANTES de ler o arquivo
                position_before_reading = self.last_event_read_position
                
                # Read only new content using the event pointer
                file_size = os.path.getsize(self.current_event_file)
                if file_size <= self.last_event_read_position:
                    return None
                file.seek(self.last_event_read_position)
                content = file.read()
                self.last_event_read_position = file.tell()

                # Scan for PRGSample pH measurement event
                for line in content.split('\n'):
                    if not line.strip():
                        continue
                        
                    parts = line.split(',')
                    if len(parts) >= 10:
                        event_type = parts[1].strip() if len(parts) > 1 else ""
                        event_number = parts[2].strip() if len(parts) > 2 else ""
                        action = parts[3].strip() if len(parts) > 3 else ""
                        
                        # Verificar todas as condições
                        if (event_type == "PRGSample" and 
                            event_number == "5" and
                            ("PRGSample pH measurement" in action or "PRGSample EC measurement" in action)):
                            
                            try:
                                ph_val = float(parts[9])  # pH Value está na coluna 10 (índice 9)
                                ec_val = float(parts[7])  # EC (ppm) está na coluna 8 (índice 7)
                                
                                # Determinar tipo de medição baseado na ação
                                measurement_type = "pH" if "pH measurement" in action else "EC"
                                
                                # Armazenar os dados do sensor
                                self.latest_sensor_data = {
                                    'time_ms': time.time() * 1000,
                                    'ph_val': ph_val,
                                    'ec_mScm': ec_val,
                                    'ph_v': float(parts[8]),  # pH (V)
                                    'ec_v': float(parts[6])   # EC (V)
                                }
                                
                                logger.info(f"Updated sensor data from event ({action}): pH={ph_val}, EC={ec_val} ppm")
                                cycle_id = self.get_current_cycle_id()
                                
                                # IMPORTANTE: Restaurar posição para garantir que possamos detectar o evento #6 mesmo se já estiver no arquivo
                                self.last_event_read_position = position_before_reading
                                logger.info(f"Pointer reset to previous position to ensure event #6 detection")
                                
                                return measurement_type, cycle_id
                            except (ValueError, IndexError) as e:
                                logger.error(f"Error parsing sensor values: {e}")
                    
                    return None
        except Exception as e:
            logger.error(f"Error detecting pH measurement from event data: {e}")
            logger.debug(traceback.format_exc())
            return None

    def check_for_prgsample_event2(self):
        """
        Detect trigger based on CSV row where 'Event Type' is "PRGSample" and 'Event' is 6.
        Uses a dedicated pointer to scan new lines from the event_data file.
        """
        if not self.current_event_file:
            return False

        try:
            with open(self.current_event_file, 'r') as file:
                file_size = os.path.getsize(self.current_event_file)
                if file_size <= self.last_event_read_position:
                    return False
                file.seek(self.last_event_read_position)
                content = file.read()
                self.last_event_read_position = file.tell()
                
                current_time = time.time()
                
                for line in content.split('\n'):
                    if not line.strip():
                        continue
                    fields = line.split(',')
                    # Expected CSV columns:
                    # 0 -> Cycle Number, 1 -> Event Type, 2 -> Event, ...
                    if len(fields) >= 3:
                        cycle_number = fields[0].strip()
                        event_type = fields[1].strip()
                        event_number = fields[2].strip()
                        
                        # Gerar ID único para o evento (combinação de timestamp e UUID)
                        event_id = f"{cycle_number}_{event_type}_{event_number}_{int(time.time())}_{str(uuid.uuid4())[:8]}"
                        
                        # Adicionar todos os eventos PRGSample ao buffer com ID único
                        if event_type == "PRGSample":
                            event_info = {
                                'event_type': event_type,
                                'event_number': event_number,
                                'cycle_id': cycle_number,
                                'timestamp': current_time,
                                'raw_data': line,
                                'event_id': event_id  # Adicionar ID único
                            }
                            self.event_buffer.append(event_info)
                            logger.debug(f"Added event to buffer: {event_type} #{event_number} for cycle {cycle_number}, ID: {event_id}")
                        
                        # Verificação específica para evento #6 com registro explícito do ID único
                        if event_type == "PRGSample" and event_number == "6":
                            # Armazenar o cycle_id e event_id do evento 6 detectado para uso posterior
                            self.last_detected_event6_cycle = cycle_number
                            self.last_detected_event6_id = event_id
                            
                            # Registrar evento no dicionário de IDs únicos
                            self.event_unique_ids[event_id] = {
                                'cycle_id': cycle_number,
                                'timestamp': current_time,
                                'processed': False
                            }
                            
                            logger.info(f"'PRGSample' with event number 6 detected for cycle {cycle_number} - ready for dosing (ID: {event_id})")
                            logger.info(f"[CYCLE_SYNC] PRGSample Event #6 belongs to cycle {cycle_number} with ID {event_id}")
                            return True
                
                return False
        except Exception as e:
            logger.error(f"Error checking for PRGSample event: {e}")
            return False

    def check_event_buffer_for_event6(self, current_cycle_id=None):
        """
        Check the event buffer for Event #6 within the timing window for the same cycle as Event #5.
        """
        if not self.event_buffer:
            return False
            
        current_time = time.time()
        cutoff_time = current_time - self.event_buffer_window_seconds
        
        # Se temos um cycle_id específico para verificar
        if current_cycle_id:
            # Verificar eventos no buffer que estejam dentro da janela de tempo E pertençam ao mesmo ciclo
            for event in self.event_buffer:
                if (event['event_type'] == "PRGSample" and 
                    event['event_number'] == "6" and 
                    event['timestamp'] >= cutoff_time and
                    event['cycle_id'] == current_cycle_id):
                    
                    # Verificar pelo ID único se este evento já foi processado
                    event_id = event.get('event_id')
                    if event_id and event_id in self.event_unique_ids:
                        if self.event_unique_ids[event_id].get('processed', False):
                            logger.debug(f"Event ID {event_id} already processed, skipping")
                            continue
                    
                    logger.info(f"Found 'PRGSample Event #6' in buffer for cycle {current_cycle_id} from {current_time - event['timestamp']:.1f} seconds ago")
                    
                    # Armazenar o cycle_id e event_id do evento 6 encontrado
                    self.last_detected_event6_cycle = event['cycle_id']
                    if 'event_id' in event:
                        self.last_detected_event6_id = event['event_id']
                        
                        # Registrar evento no dicionário de IDs únicos se ainda não existir
                        if event['event_id'] not in self.event_unique_ids:
                            self.event_unique_ids[event['event_id']] = {
                                'cycle_id': event['cycle_id'],
                                'timestamp': current_time,
                                'processed': False
                            }
                    
                    return True
        
        return False

    def is_event_already_processed(self, cycle_id, event_id=None):
        """
        Verifica se um evento já foi processado com base no cycle_id e/ou event_id.
        """
        # Se temos um ID de evento único, usar isso como verificação primária
        if event_id and event_id in self.event_unique_ids:
            if self.event_unique_ids[event_id].get('processed', False):
                logger.info(f"Evento com ID único {event_id} já foi processado anteriormente")
                return True
        
        # Verificação de fallback baseada no cycle_id (para compatibilidade)
        if not cycle_id:
            return False
            
        # Verificar se este ciclo já foi processado
        if cycle_id in self.processed_events:
            now = time.time()
            last_processed = self.processed_events[cycle_id]
            # Considerar processado se foi nos últimos 10 minutos
            if now - last_processed < 600:  # 10 minutos em segundos
                logger.info(f"Evento para ciclo {cycle_id} já foi processado em {datetime.fromtimestamp(last_processed).strftime('%H:%M:%S')}")
                return True
        
        return False

    def _find_recent_valid_data(self):
        """Find recent valid non-zero sensor data in the file"""
        try:
            if not self.current_data_file:
                return False
            
            with open(self.current_data_file, 'r') as file:
                # Skip header
                header = file.readline()
                
                # Read all lines (or last N lines for efficiency)
                lines = file.readlines()[-100:]  # Get last 100 lines
                
                # Process in reverse to find most recent valid data
                for line in reversed(lines):
                    parts = line.strip().split(',')
                    if len(parts) >= 8:
                        try:
                            # Extract values
                            time_ms = float(parts[0]) if parts[0].strip() else time.time() * 1000
                            ec_v = float(parts[4]) if len(parts) > 4 and parts[4].strip() else None
                            ec_mScm = float(parts[5]) if len(parts) > 5 and parts[5].strip() else None
                            ph_v = float(parts[6]) if len(parts) > 6 and parts[6].strip() else None
                            ph_val = float(parts[7]) if len(parts) > 7 and parts[7].strip() else None
                            
                            # Skip if any value is missing, zero or invalid
                            if (ec_v is None or ec_mScm is None or ph_v is None or ph_val is None or
                                ec_mScm <= 0 or ph_val <= 0):
                                continue
                            
                            # Store these values
                            self.latest_sensor_data = {
                                'time_ms': time_ms,
                                'ec_v': ec_v,
                                'ec_mScm': ec_mScm,
                                'ph_v': ph_v,
                                'ph_val': ph_val
                            }
                            
                            logger.info(f"Found valid sensor data: pH={ph_val:.2f}, EC={ec_mScm:.2f} mS/cm")
                            return True
                            
                        except (ValueError, IndexError):
                            continue
                            
            logger.warning("No valid non-zero sensor data found in file")
            return False
        except Exception as e:
            logger.error(f"Error finding valid sensor data: {e}")
            return False

    def get_current_cycle_id(self):
        """
        Extract the cycle ID directly from the event data file.
        """
        try:
            if not self.current_event_file:
                self.current_event_file = self.find_latest_event_file()
                if not self.current_event_file:
                    # Fallback to internal counter if no file
                    if not hasattr(self, 'cycle_counter'):
                        self.cycle_counter = 1
                    else:
                        self.cycle_counter += 1
                    return str(self.cycle_counter)
            
            # Ler o arquivo para encontrar o último Cycle Number preenchido
            with open(self.current_event_file, 'r') as file:
                # Pular cabeçalho
                header = file.readline()
                
                last_cycle_number = None
                
                # Ler todo o arquivo para encontrar o último Cycle Number não vazio
                for line in file:
                    if not line.strip():
                        continue
                        
                    parts = line.split(',')
                    if len(parts) >= 1 and parts[0].strip():
                        try:
                            cycle_number = parts[0].strip()
                            # Verificar se é um número válido
                            int(cycle_number)  # Apenas para validação
                            last_cycle_number = cycle_number
                        except ValueError:
                            # Não é um número válido, ignorar
                            continue
                
                # Se encontramos um número de ciclo, use-o; caso contrário, use o contador interno
                if last_cycle_number is not None:
                    logger.debug(f"Extracted cycle ID from file: {last_cycle_number}")
                    return last_cycle_number
                else:
                    # Fallback para contador interno
                    if not hasattr(self, 'cycle_counter'):
                        self.cycle_counter = 1
                    else:
                        self.cycle_counter += 1
                    return str(self.cycle_counter)
                    
        except Exception as e:
            logger.error(f"Error extracting cycle ID from file: {e}")
            # Fallback para contador interno
            if not hasattr(self, 'cycle_counter'):
                self.cycle_counter = 1
            else:
                self.cycle_counter += 1
            return str(self.cycle_counter)

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
            if entry['ec_mScm'] is not None and entry['action'] == 'reading'
        ]
        
        if len(recent_readings) < 2:
            return None
        
        # Calculate time difference in seconds and EC difference
        time_diff = (recent_readings[-1]['time_ms'] - recent_readings[-2]['time_ms']) / 1000
        ec_diff = recent_readings[-2]['ec_mScm'] - recent_readings[-1]['ec_mScm']
        
        if time_diff <= 0:
            return None
        
        # EC depletion rate in mS/cm/hour
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
            self.latest_sensor_data['ec_mScm'],
            abs(self.latest_sensor_data['ph_val'] - self.config['target_ph']) if self.latest_sensor_data['ph_val'] is not None else 0,
            abs(self.latest_sensor_data['ec_mScm'] - self.config['target_ec']),
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

    def update_titration_coefficients(self):
        """Update titration coefficients based on previous cycle's dosing effect"""
        # Skip if we don't have previous cycle data
        if (self.last_cycle_id is None or self.last_cycle_dosing is None or
            self.last_cycle_ph_value is None or self.last_cycle_ec_value is None):
            logger.info("No previous cycle data available for coefficient learning")
            return
            
        # Get current values
        current_ph = self.latest_sensor_data.get('ph_val')
        current_ec = self.latest_sensor_data.get('ec_mScm')
        
        if current_ph is None or current_ec is None:
            logger.warning("Current sensor readings incomplete, can't update coefficients")
            return
            
        # Extract info from last dosing
        pump_type = self.last_cycle_dosing.get('pump')
        volume_dosed = self.last_cycle_dosing.get('volume')
        
        if not pump_type or not volume_dosed:
            logger.warning("Missing pump type or volume from last dosing")
            return
            
        # Calculate observed change
        if pump_type.startswith('ph'):
            observed_change = abs(current_ph - self.last_cycle_ph_value)
            logger.info(f"Observed pH change: {observed_change:.3f} from {volume_dosed:.2f}mL of {pump_type}")
            
            # Skip if no significant change
            if observed_change < 0.01:
                logger.info("Observed change too small, skipping coefficient update")
                return
                
            # Calculate effect per mL (Titration Coefficient)
            effect_per_ml = observed_change / volume_dosed
            
            # Update titration coefficient with learning rate 0.5
            learning_rate = 0.5  # Higher learning rate as requested
            
            if pump_type == "ph_plus":
                current_coefficient = self.ph_plus_titration_coefficient
                new_coefficient = current_coefficient * (1 - learning_rate) + (effect_per_ml * learning_rate)
                self.ph_plus_titration_coefficient = new_coefficient
                # Also update in config for consistency
                self.config['ph_plus_molarity'] = new_coefficient
                logger.info(f"Updated pH+ Titration Coefficient: {current_coefficient:.4f} → {new_coefficient:.4f}")
                
            elif pump_type == "ph_minus":
                current_coefficient = self.ph_minus_titration_coefficient
                new_coefficient = current_coefficient * (1 - learning_rate) + (effect_per_ml * learning_rate)
                self.ph_minus_titration_coefficient = new_coefficient
                # Also update in config for consistency
                self.config['ph_minus_molarity'] = new_coefficient
                logger.info(f"Updated pH- Titration Coefficient: {current_coefficient:.4f} → {new_coefficient:.4f}")
                
        elif pump_type == "ec_plus":
            observed_change = abs(current_ec - self.last_cycle_ec_value)
            logger.info(f"Observed EC change: {observed_change:.3f} mS/cm from {volume_dosed:.2f}mL")
            
            # Skip if no significant change
            if observed_change < 0.01:
                logger.info("Observed change too small, skipping coefficient update")
                return
                
            # Calculate mL per L per EC change
            ml_per_l_per_ec = volume_dosed / (observed_change * self.config['tank_volume_liters'])
            
            # Update EC coefficient with learning rate 0.5
            learning_rate = 0.5
            current_coefficient = self.ec_specific_conductivity_coefficient
            new_coefficient = current_coefficient * (1 - learning_rate) + (ml_per_l_per_ec * learning_rate)
            self.ec_specific_conductivity_coefficient = new_coefficient
            # Also update in config for consistency
            self.config['ec_up_volume_per_ec'] = new_coefficient
            logger.info(f"Updated EC Specific Conductivity Coefficient: {current_coefficient:.2f} → {new_coefficient:.2f}")

    def calculate_chemical_dosing_volume(self, pump_type):
        """Calculate the required volume for chemical dosing based on current readings and target values"""
        if not self.latest_sensor_data:
            logger.warning("No sensor data available for chemical calculations")
            return 0, 0
            
        # Get the current pH and EC values
        current_ph = self.latest_sensor_data.get('ph_val')
        current_ec = self.latest_sensor_data.get('ec_mScm')
        
        # Safety checks
        if current_ph is None or current_ec is None:
            return 0, 0
        
        # Calculate tank volume in milliliters
        tank_volume_ml = self.config['tank_volume_liters'] * 1000
        
        # Calculate the required volume based on pump type
        if pump_type == "ph_plus":
            # Calculate pH+ volume based on pH difference and titration coefficient
            ph_difference = self.config['target_ph'] - current_ph
            if ph_difference <= 0:
                logger.info(f"No pH+ needed: current {current_ph:.2f} >= target {self.config['target_ph']}")
                return 0, 0
                
            # Use titration coefficient (pH units per mL)
            ml_needed = ph_difference / self.ph_plus_titration_coefficient
            logger.info(f"pH+ calculation: Target: {self.config['target_ph']}, Current: {current_ph:.2f}, Difference: {ph_difference:.2f}")
            logger.info(f"Using pH+ titration coefficient: {self.ph_plus_titration_coefficient:.4f} pH units/mL")
            logger.info(f"Calculated pH+ volume: {ml_needed:.2f} mL")
            
            # Convert to dosing time
            dosing_time = self.convert_volume_to_dosing_time(ml_needed)
            return dosing_time, ml_needed
            
        elif pump_type == "ph_minus":
            # Calculate pH- volume based on pH difference and titration coefficient
            ph_difference = current_ph - self.config['target_ph']
            if ph_difference <= 0:
                logger.info(f"No pH- needed: current {current_ph:.2f} <= target {self.config['target_ph']}")
                return 0, 0
                
            # Use titration coefficient (pH units per mL)
            ml_needed = ph_difference / self.ph_minus_titration_coefficient
            logger.info(f"pH- calculation: Target: {self.config['target_ph']}, Current: {current_ph:.2f}, Difference: {ph_difference:.2f}")
            logger.info(f"Using pH- titration coefficient: {self.ph_minus_titration_coefficient:.4f} pH units/mL")
            logger.info(f"Calculated pH- volume: {ml_needed:.2f} mL")
            
            # Convert to dosing time
            dosing_time = self.convert_volume_to_dosing_time(ml_needed)
            return dosing_time, ml_needed
            
        elif pump_type == "ec_plus":
            # Calculate EC+ volume based on EC difference and conductivity coefficient
            ec_difference = self.config['target_ec'] - current_ec
            if ec_difference <= 0:
                logger.info(f"No EC+ needed: current {current_ec:.2f} >= target {self.config['target_ec']}")
                return 0, 0
                
            # Calculate mL needed based on EC conductivity coefficient
            # The coefficient is: mL per L per 1.0 mS/cm increase
            ml_needed = ec_difference * self.ec_specific_conductivity_coefficient * self.config['tank_volume_liters']
            logger.info(f"EC+ calculation: Target: {self.config['target_ec']}, Current: {current_ec:.2f}, Difference: {ec_difference:.2f}")
            logger.info(f"Using EC conductivity coefficient: {self.ec_specific_conductivity_coefficient:.2f} mL/L/mS/cm")
            logger.info(f"Calculated EC+ volume: {ml_needed:.2f} mL")
            
            # Convert to dosing time
            dosing_time = self.convert_volume_to_dosing_time(ml_needed)
            return dosing_time, ml_needed
        
        return 0, 0

    def convert_volume_to_dosing_time(self, volume_ml):
        """Convert volume in mL to dosing time in milliseconds based on pump flow rate"""
        if volume_ml <= 0:
            return 0
            
        # Flow rate is in ml/min, convert to ml/ms
        flow_rate_ml_per_ms = self.config['pump_flow_rate'] / (60 * 1000)
        
        # Apply calibration factor
        adjusted_flow_rate = flow_rate_ml_per_ms * self.config['flow_calibration_factor']
        
        # Calculate time in ms required for the volume
        dosing_time_ms = int(volume_ml / adjusted_flow_rate)
        
        # Ensure within min/max limits
        dosing_time_ms = max(self.config['min_dosing_time_ms'], min(dosing_time_ms, self.config['max_dosing_time_ms']))
        
        logger.info(f"Converted {volume_ml:.2f} mL to {dosing_time_ms} ms dosing time (flow rate: {self.config['pump_flow_rate']:.1f} mL/min)")
        
        return dosing_time_ms

    def chemistry_based_dosing_decision(self, measurement_type):
        """Make dosing decisions based on chemical calculations with cycle-based safety factors"""
        if not self.config.get('chemistry_based_dosing', True):
            return None
            
        if not self.latest_sensor_data:
            logger.warning("No sensor data available for chemistry-based dosing decision")
            return None
                
        ph_val = self.latest_sensor_data.get('ph_val')
        ec_mScm = self.latest_sensor_data.get('ec_mScm')
        
        # Validations
        if ph_val is None or ec_mScm is None:
            logger.warning(f"Incomplete sensor data: pH={ph_val}, EC={ec_mScm}")
            return None
            
        # Check deviations
        ph_deviation = abs(ph_val - self.config['target_ph'])
        ec_deviation = abs(ec_mScm - self.config['target_ec'])
        
        logger.info(f"Chemistry analysis - pH: {ph_val:.2f} (deviation: {ph_deviation:.2f}), EC: {ec_mScm:.2f} mS/cm (deviation: {ec_deviation:.2f})")
        
        # First priority: Check if EC needs correction
        if ec_deviation > self.config['ec_tolerance']:
            if ec_mScm < self.config['target_ec']:
                # EC is low, calculate volume needed for EC+
                _, volume_needed = self.calculate_chemical_dosing_volume("ec_plus")
                
                # NEW LOGIC: Check if this is the first dosing
                ec_dosing_count = len([e for e in self.dosing_history if e.get('pump') == 'ec_plus'])
                
                if ec_dosing_count == 0:
                    # First time dosing - divide by 10
                    volume_needed /= 10
                    logger.info(f"First EC+ dosing: dividing volume by 10: {volume_needed:.2f} mL")
                else:
                    # Subsequent dosing - divide by 2
                    volume_needed /= 2
                    logger.info(f"Subsequent EC+ dosing: dividing volume by 2: {volume_needed:.2f} mL")
                
                # Convert to dosing time
                dosing_time = self.convert_volume_to_dosing_time(volume_needed)
                
                # Ensure minimum dosing time
                if dosing_time < self.config['min_dosing_time_ms']:
                    dosing_time = self.config['min_dosing_time_ms']
                    logger.info(f"Adjusting to minimum dosing time: {dosing_time} ms")
                
                if dosing_time >= self.config['min_dosing_time_ms']:
                    logger.info(f"Chemistry decision: Increase EC with {volume_needed:.2f} mL ({dosing_time} ms)")
                    return "ec_plus", dosing_time, volume_needed
        
        # Second priority: Check if pH needs correction
        if ph_deviation > self.config['ph_tolerance']:
            # Determine which pH adjustment is needed
            if ph_val < self.config['target_ph']:
                # pH is low, calculate volume needed for pH+
                _, volume_needed = self.calculate_chemical_dosing_volume("ph_plus")
                
                # NEW LOGIC: Check if this is the first dosing
                ph_plus_dosing_count = len([e for e in self.dosing_history if e.get('pump') == 'ph_plus'])
                
                if ph_plus_dosing_count == 0:
                    # First time dosing - divide by 10
                    volume_needed /= 10
                    logger.info(f"First pH+ dosing: dividing volume by 10: {volume_needed:.2f} mL")
                else:
                    # Subsequent dosing - divide by 2
                    volume_needed /= 2
                    logger.info(f"Subsequent pH+ dosing: dividing volume by 2: {volume_needed:.2f} mL")
                
                # Convert to dosing time
                dosing_time = self.convert_volume_to_dosing_time(volume_needed)
                
                # Ensure minimum dosing time
                if dosing_time < self.config['min_dosing_time_ms']:
                    dosing_time = self.config['min_dosing_time_ms']
                    logger.info(f"Adjusting to minimum dosing time: {dosing_time} ms")
                
                if dosing_time >= self.config['min_dosing_time_ms']:
                    logger.info(f"Chemistry decision: Increase pH with {volume_needed:.2f} mL ({dosing_time} ms)")
                    return "ph_plus", dosing_time, volume_needed
                    
            else:
                # pH is high, calculate volume needed for pH-
                _, volume_needed = self.calculate_chemical_dosing_volume("ph_minus")
                
                # NEW LOGIC: Check if this is the first dosing
                ph_minus_dosing_count = len([e for e in self.dosing_history if e.get('pump') == 'ph_minus'])
                
                if ph_minus_dosing_count == 0:
                    # First time dosing - divide by 10
                    volume_needed /= 10
                    logger.info(f"First pH- dosing: dividing volume by 10: {volume_needed:.2f} mL")
                else:
                    # Subsequent dosing - divide by 2
                    volume_needed /= 2
                    logger.info(f"Subsequent pH- dosing: dividing volume by 2: {volume_needed:.2f} mL")
                
                # Convert to dosing time
                dosing_time = self.convert_volume_to_dosing_time(volume_needed)
                
                # Ensure minimum dosing time
                if dosing_time < self.config['min_dosing_time_ms']:
                    dosing_time = self.config['min_dosing_time_ms']
                    logger.info(f"Adjusting to minimum dosing time: {dosing_time} ms")
                
                if dosing_time >= self.config['min_dosing_time_ms']:
                    logger.info(f"Chemistry decision: Decrease pH with {volume_needed:.2f} mL ({dosing_time} ms)")
                    return "ph_minus", dosing_time, volume_needed
        
        logger.info("Chemistry decision: No dosing needed, parameters within tolerance")
        return None

    def calculate_adaptive_timeout(self):
        """Calculate an adaptive timeout based on historical cycle times"""
        if not hasattr(self, 'cycle_time_history'):
            self.cycle_time_history = []
        
        # Default timeout if we don't have history
        default_timeout = 900  # 15 minutes
        
        if len(self.cycle_time_history) < 2:
            # Not enough data for adaptive calculation, use default
            logger.info(f"Using default timeout of {default_timeout} seconds")
            return default_timeout
        
        # Calculate average cycle time from history
        avg_cycle_time = sum(self.cycle_time_history) / len(self.cycle_time_history)
        
        # Add a 20% buffer to account for variations
        adaptive_timeout = int(avg_cycle_time * 1.2)
        
        # Enforce minimum and maximum bounds
        min_timeout = 300  # 5 minutes
        max_timeout = 1800  # 30 minutes
        
        adaptive_timeout = max(min_timeout, min(adaptive_timeout, max_timeout))
        
        logger.info(f"Adaptive timeout calculated: {adaptive_timeout} seconds (based on {len(self.cycle_time_history)} previous cycles)")
        return adaptive_timeout

    def detect_prg_events(self):
        """Detect PRGCal and other calibration events in the event_data CSV"""
        if not self.current_event_file:
            return None

        try:
            with open(self.current_event_file, 'r') as file:
                file_size = os.path.getsize(self.current_event_file)
                if file_size <= self.last_event_read_position:
                    return None
                
                file.seek(self.last_event_read_position)
                content = file.read()
                self.last_event_read_position = file.tell()

                for line in content.split('\n'):
                    if not line.strip() or "Cycle Number,Event Type" in line:  # Skip header and empty lines
                        continue
                    
                    parts = line.split(',')
                    if len(parts) >= 2:
                        event_type = parts[1].strip().lower()  # Convert to lowercase for comparison
                        
                        if "prgcal" in event_type:  # Case-insensitive partial match
                            self.in_prgcal = True
                            logger.info(f"PRGCal calibration in progress - dosing suspended. Found: {parts[1]}")
                            return "calibration"
                        elif event_type == "prgsample" or parts[1].strip() == "PRGSample":
                            self.in_prgcal = False
                            logger.info(f"PRGSample detected - resuming normal dosing operation. Found: {parts[1]}")
                            return None
            
                return None

        except Exception as e:
            logger.error(f"Error detecting PRG events: {e}")
            return None

    def initialize_event_detection(self):
        """Check for existing events in the file at startup"""
        if not self.current_event_file:
            return
        
        try:
            # Reset position to start of file
            temp_position = 0
            last_event_type = None
            
            logger.info("Scanning entire event file to determine current state...")
            
            with open(self.current_event_file, 'r') as file:
                # Primeira linha é o cabeçalho
                header = file.readline()
                
                # Ler o arquivo inteiro para encontrar o último evento
                for line in file:
                    if not line.strip():
                        continue
                        
                    parts = line.split(',')
                    if len(parts) >= 2:
                        event_type = parts[1].strip()
                        if "prgcal" in event_type.lower():
                            last_event_type = "PRGcal"
                        elif "prgsample" in event_type.lower():
                            last_event_type = "PRGSample"
            
            # Definir o estado com base no último evento encontrado
            if last_event_type == "PRGcal":
                self.in_prgcal = True
                logger.info("Last event was PRGcal - dosing suspended")
            elif last_event_type == "PRGSample":
                self.in_prgcal = False
                logger.info("Last event was PRGSample - normal operation")
            else:
                logger.info("No PRG events found in file")
                
            # Definir posição para ler apenas novos eventos
            self.last_event_read_position = os.path.getsize(self.current_event_file)
                
        except Exception as e:
            logger.error(f"Error initializing event detection: {e}")

    def send_dosing_command(self, pump_type, dosing_time, volume_needed):
        """Send dosing command to the pump controller"""
        try:
            if pump_type == "ph_plus":
                pin = self.config['ph_plus_pin']
            elif pump_type == "ph_minus":
                pin = self.config['ph_minus_pin']
            elif pump_type == "ec_plus":
                pin = self.config['ec_plus_pin']
            else:
                logger.error(f"Unknown pump type: {pump_type}")
                return False

            # Build JSON command with all required fields (including action and volume)
            command = {
                "action": "dose",                       # Added field
                "command": "activate_pump",
                "pin": pin,
                "duration_ms": dosing_time,
                "pump_type": pump_type,
                "message_id": int(time.time() * 1000),    # Critical field
                "volume": volume_needed                   # Added field (required by dashboard)
            }

            if self.dashboard_socket:
                try:
                    logger.info(f"Sending command to activate {pump_type} on pin {pin} for {dosing_time}ms with volume {volume_needed:.2f} mL")
                    self.dashboard_socket.send_json(command)
                    
                    poller = zmq.Poller()
                    poller.register(self.dashboard_socket, zmq.POLLIN)
                    timeout = self.config.get('zmq_timeout_ms', 5000)
                    
                    logger.info(f"Waiting for response (timeout: {timeout}ms)")
                    events = dict(poller.poll(timeout))
                    
                    if self.dashboard_socket in events:
                        response = self.dashboard_socket.recv_json()
                        if response.get('success'):
                            logger.info(f"Received successful response for {pump_type} activation")
                            return True
                        else:
                            error_msg = response.get('error', 'Unknown error')
                            logger.error(f"Command failed: {error_msg}")
                            return False
                    else:
                        logger.warning(f"Timeout waiting for response to {pump_type} command")
                        return False
                        
                except zmq.ZMQError as e:
                    logger.error(f"ZMQ communication error: {e}")
                    return False
            else:
                logger.warning("No ZMQ socket available for dosing command")
                return False
                
        except Exception as e:
            logger.error(f"Error sending dosing command: {e}")
            logger.debug(traceback.format_exc())
            return False

    def append_to_csv(self, pump_type, dosing_time):
        """Append dosing action to CSV record"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get current readings
        ph_val = self.latest_sensor_data.get('ph_val', 'N/A') if self.latest_sensor_data else 'N/A'
        ec_val = self.latest_sensor_data.get('ec_mScm', 'N/A') if self.latest_sensor_data else 'N/A'
        
        # Get volume based on dosing time (approximate)
        flow_rate_ml_per_ms = self.config['pump_flow_rate'] / (60 * 1000)
        volume_ml = dosing_time * flow_rate_ml_per_ms
        
        # Add to history
        self.dosing_history.append({
            'time': timestamp,
            'time_ms': time.time() * 1000,
            'action': 'dosing',
            'pump': pump_type,
            'dosing_time_ms': dosing_time,
            'volume_ml': volume_ml,
            'ph_val': ph_val,
            'ec_mScm': ec_val
        })
        
        # Write to CSV
        csv_path = os.path.join(self.config['data_dir'], 'dosing_history.csv')
        file_exists = os.path.exists(csv_path)
        
        try:
            with open(csv_path, 'a', newline='') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header if file is new
                if not file_exists:
                    writer.writerow(['Timestamp', 'Pump', 'Dosing Time (ms)', 'Volume (mL)', 'pH', 'EC (mS/cm)'])
                
                # Write data
                writer.writerow([timestamp, pump_type, dosing_time, f"{volume_ml:.2f}", ph_val, ec_val])
                
            logger.info(f"Recorded dosing action to CSV: {pump_type}, {dosing_time}ms, {volume_ml:.2f}mL")
            return True
        except Exception as e:
            logger.error(f"Failed to write to dosing history CSV: {e}")
            return False

    def run(self):
        """Main loop with cycle-based detection and dosing logic"""
        # Add this line to initialize event detection
        self.initialize_event_detection()
        
        while self.running:
            try:
                # Limpar eventos processados antigos (mais de 1 hora)
                current_time = time.time()
                old_events = [cycle for cycle, timestamp in self.processed_events.items() 
                             if current_time - timestamp > 3600]  # 1 hora em segundos
                for cycle in old_events:
                    del self.processed_events[cycle]

                # Adicionar limpeza de IDs únicos antigos
                old_event_ids = [event_id for event_id, data in self.event_unique_ids.items() 
                                if current_time - data.get('timestamp', 0) > 3600]  # 1 hora em segundos
                for event_id in old_event_ids:
                    del self.event_unique_ids[event_id]

                if old_events or old_event_ids:
                    logger.debug(f"Removidos {len(old_events)} ciclos e {len(old_event_ids)} IDs de eventos antigos do rastreador")

                # STEP 1: Look for "PRGSample pH measurement" in CSV
                measurement_result = self.detect_prgsample_ph_measurement()

                # ADICIONAR AQUI:
                # Verificar se estamos em calibração antes de prosseguir
                if self.in_prgcal:
                    logger.info("Skipping dosing cycle - PRGcal calibration in progress")
                    time.sleep(1)
                    continue
                
                if measurement_result:
                    measurement_type, cycle_id = measurement_result
                    logger.info(f"EVENT: {measurement_type} measurement detected - Cycle ID: {cycle_id}")
                    
                    # Adicionar verificação de ciclo mínimo
                    if int(cycle_id) < 2:
                        logger.info(f"Skipping dosing - Current cycle {cycle_id} is less than minimum required cycle (2)")
                        
                        # Apenas atualizar dados do ciclo para manter continuidade
                        self.last_cycle_id = cycle_id
                        self.last_cycle_ph_value = self.latest_sensor_data.get('ph_val')
                        self.last_cycle_ec_value = self.latest_sensor_data.get('ec_mScm')
                        time.sleep(1)
                        continue
                    
                    # Os dados do sensor já foram atualizados pelo detect_prgsample_ph_measurement()
                    logger.info("Using sensor data from event_data.csv")
                    
                    # STEP 2: Ensure we have valid sensor data
                    if not self.latest_sensor_data:
                        logger.warning("No valid sensor data available after measurement detection")
                        time.sleep(1)
                        continue
                    
                    # Store current sensor values for next cycle's learning
                    current_ph = self.latest_sensor_data.get('ph_val')
                    current_ec = self.latest_sensor_data.get('ec_mScm')

                    # Registrar explicitamente os valores atuais para garantir sincronização
                    logger.info(f"Current sensor readings: pH={current_ph:.2f}, EC={current_ec:.2f}")
                    
                    if current_ph is None or current_ec is None:
                        logger.warning(f"Incomplete sensor readings: pH={current_ph}, EC={current_ec}")
                        time.sleep(1)
                        continue
                    
                    # STEP 3: Update titration coefficients from previous cycle's effect
                    if self.last_cycle_id is not None and cycle_id != self.last_cycle_id:
                        self.update_titration_coefficients()
                    
                    # STEP 4 & 5: Calculate dosing volume with appropriate safety factor
                    dosing_result = self.chemistry_based_dosing_decision(measurement_type)
                    
                    if dosing_result:
                        pump_type, dosing_time, volume_needed = dosing_result
                        
                        # STEP 6: Wait for "PRGSample Event #6"
                        logger.info(f"Waiting for 'PRGSample event #6' for cycle {cycle_id} to dose...")

                        # Armazenar o cycle_id atual para sincronização de eventos
                        self.current_processing_cycle_id = cycle_id

                        # Verificar se já temos um evento #6 do MESMO CICLO no buffer
                        if self.check_event_buffer_for_event6(cycle_id):  # Passar o cycle_id atual
                            event_detected = True
                            logger.info(f"'PRGSample Event #6' already found in buffer for cycle {cycle_id}, proceeding with dosing!")
                        else:
                            # Wait loop for "PRGSample Event #6" of the same cycle
                            event_detected = False
                            start_time = time.time()
                            wait_time = self.calculate_adaptive_timeout()
                            
                            while not event_detected and (time.time() - start_time < wait_time):
                                # Check if event #6 was detected for the current cycle
                                if self.check_for_prgsample_event2():
                                    # Verificar se o evento #6 detectado pertence ao ciclo atual
                                    if hasattr(self, 'last_detected_event6_cycle') and self.last_detected_event6_cycle == cycle_id:
                                        event_detected = True
                                        logger.info(f"'PRGSample Event #6' detected for cycle {cycle_id}, proceeding with dosing!")
                                        break
                                    else:
                                        logger.warning(f"Detected Event #6 for cycle {getattr(self, 'last_detected_event6_cycle', 'unknown')}, but waiting for cycle {cycle_id}")
                                
                                # Verificar no buffer novamente (pode ter sido adicionado por outra detecção)
                                if self.check_event_buffer_for_event6(cycle_id):
                                    event_detected = True
                                    logger.info(f"'PRGSample Event #6' found in buffer for cycle {cycle_id} during wait loop")
                                    break
                                    
                                time.sleep(0.5)
                        
                        if event_detected and hasattr(self, 'last_event2_time'):
                            # Calculate the time elapsed since last Event #6 detection
                            current_time = time.time()
                            cycle_duration = current_time - self.last_event2_time
                            
                            # Add to history
                            if not hasattr(self, 'cycle_time_history'):
                                self.cycle_time_history = []
                            
                            # Only record reasonable cycle times (between 1 and 30 minutes)
                            if 60 <= cycle_duration <= 1800:
                                self.cycle_time_history.append(cycle_duration)
                                # Keep only most recent 10 cycles
                                if len(self.cycle_time_history) > 10:
                                    self.cycle_time_history = self.cycle_time_history[-10:]
                                logger.info(f"Recorded cycle duration: {cycle_duration:.0f} seconds")
                            
                            # Update last detection time
                            self.last_event2_time = current_time
                        else:
                            # First detection
                            self.last_event2_time = time.time()
                        
                        if not event_detected:
                            logger.warning(f"Timeout waiting for 'PRGSample Event #6' after {wait_time} seconds")
                            time.sleep(1)
                            continue
                        
                        if event_detected:
                            # Verificar se este evento já foi processado usando ID único se disponível
                            event_id = getattr(self, 'last_detected_event6_id', None)
                            if self.is_event_already_processed(cycle_id, event_id):
                                logger.warning(f"Evento #6 para o ciclo {cycle_id}" + (f" com ID {event_id}" if event_id else "") + " já foi processado anteriormente. Ignorando.")
                                continue
                        
                        # STEP 7: Dose the calculated volume
                        logger.info(f"DOSING: Activating {pump_type} pump for {dosing_time}ms")
                        success = self.send_dosing_command(pump_type, dosing_time, volume_needed)
                        
                        if success:
                            # Registrar este evento como processado pelo cycle_id
                            self.processed_events[cycle_id] = time.time()
                            
                            # Registrar evento como processado pelo ID único, se disponível
                            event_id = getattr(self, 'last_detected_event6_id', None)
                            if event_id and event_id in self.event_unique_ids:
                                self.event_unique_ids[event_id]['processed'] = True
                                self.event_unique_ids[event_id]['processed_timestamp'] = time.time()
                                logger.info(f"Marcado evento com ID {event_id} como processado")
                            
                            # Store dosing info for next cycle's learning
                            self.last_cycle_dosing = {
                                'pump': pump_type,
                                'volume': volume_needed,
                                'time_ms': dosing_time
                            }
                            self.last_cycle_id = cycle_id
                            self.last_cycle_ph_value = current_ph
                            self.last_cycle_ec_value = current_ec
                            
                            logger.info(f"SUCCESS: {pump_type} dosing complete - Volume: {volume_needed:.2f} mL")
                            self.append_to_csv(pump_type, dosing_time)
                        else:
                            logger.error(f"FAILURE: {pump_type} dosing failed")
                    else:
                        # Even if no dosing, update cycle info for continuity
                        if self.last_cycle_id is None:
                            logger.info("Initializing cycle learning data")
                        # Update these so that the learning mechanism always has past cycle data
                        self.last_cycle_id = cycle_id
                        self.last_cycle_ph_value = current_ph
                        self.last_cycle_ec_value = current_ec
                        logger.info(f"NO DOSING NEEDED in this cycle ({cycle_id}); cycle data updated for learning")
                        continue  # Proceed to next cycle
                
                # Continue to detect other PRG events such as calibrations
                self.detect_prg_events()
                
                # Brief pause to avoid excessive CPU usage
                time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in control loop: {e}")
                logger.debug(traceback.format_exc())
                time.sleep(5)  # Longer pause in case of error

# Main execution block
if __name__ == "__main__":
    try:
        # Create data directory if it doesn't exist
        data_dir = CONFIG["data_dir"]
        os.makedirs(data_dir, exist_ok=True)
        
        # Create and run the controller
        controller = DosingController()
        logger.info("Starting dosing controller...")
        controller.run()
    except KeyboardInterrupt:
        logger.info("Controller stopped by user")
    except Exception as e:
        logger.error(f"Error starting controller: {e}")
        logger.debug(traceback.format_exc())
    finally:
        # Clean shutdown
        logger.info("Shutting down controller")
        if 'controller' in locals() and controller is not None:
            controller.running = False