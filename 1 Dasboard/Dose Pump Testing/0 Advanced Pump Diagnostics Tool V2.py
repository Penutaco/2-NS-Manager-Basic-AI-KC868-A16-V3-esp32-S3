#!/usr/bin/env python3
"""
Improved Pump Control Diagnostic Tool

This tool provides a solution to the pump control communication issues:
1. Tests working command formats
2. Implements a bridge between ZMQ and Serial
3. Provides sample code for the ESP32 firmware
"""

import serial
import time
import json
import logging
import sys
import zmq
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("improved_pump_control.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ImprovedPumpControl")

# Configuration
SERIAL_PORT = '/dev/cu.usbserial-110'
BAUD_RATE = 115200
ZMQ_SERVER = "tcp://localhost:5555"

# Pump pins
PIN_PH_PLUS = 27
PIN_PH_MINUS = 26
PIN_EC = 25

class ImprovedPumpControl:
    def __init__(self):
        self.serial_conn = None
        self.zmq_context = None
        self.zmq_socket = None
        
    def setup(self):
        """Initialize connections"""
        logger.info("Starting improved pump control tool...")
        
        # Try to establish serial connection
        try:
            self.serial_conn = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)  # Allow time for serial connection to stabilize
            logger.info(f"Serial connection established on {SERIAL_PORT}")
        except Exception as e:
            logger.error(f"Failed to establish serial connection: {e}")
            self.serial_conn = None
            return False
            
        return True
    
    def test_format_variations(self, pin, duration_ms):
        """Test various command formats to find what works"""
        if not self.serial_conn:
            logger.error("Serial connection not available")
            return
            
        # List of command formats to try
        commands = [
            # Format 1: Simple text with newline
            f"PUMP:{pin}:{duration_ms}\n",
            
            # Format 2: JSON with command, pin, duration
            json.dumps({"command": "pump", "pin": pin, "duration": duration_ms}) + "\n",
            
            # Format 3: JSON with action, pin, duration
            json.dumps({"action": "pump", "pin": pin, "duration": duration_ms}) + "\n",
            
            # Format 4: Arduino-style command
            f"DOSING:{pin}:{duration_ms}\n",
            
            # Format 5: Direct pin control
            f"DIGITALWRITE:{pin}:1\n",
            
            # Format 6: Different format - simple text
            f"ACTIVATE_PUMP {pin} {duration_ms}\n"
        ]
        
        # Try each command format
        logger.info(f"Testing {len(commands)} command format variations for pin {pin}")
        
        for i, cmd in enumerate(commands):
            logger.info(f"Testing format {i+1}: {cmd.strip()}")
            self.serial_conn.write(cmd.encode())
            time.sleep(0.1)  # Wait for processing
            
            # Send off signal if format 5 (DIGITALWRITE)
            if i == 4:
                time.sleep(duration_ms/1000)  # Wait for duration
                off_cmd = f"DIGITALWRITE:{pin}:0\n"
                self.serial_conn.write(off_cmd.encode())
            
            time.sleep(0.5)  # Wait for response
            response = self.serial_conn.read_all().decode('utf-8', errors='ignore')
            
            if response:
                logger.info(f"Received response: {response}")
            else:
                logger.info("No response received")
    
    def generate_esp32_code(self):
        """Generate ESP32 code for handling dosing commands"""
        esp32_code = """
// Add this implementation to your main.cpp file

// Implementation of handleDosingCommand
void handleDosingCommand(String command) {
  Serial.print("Received command: ");
  Serial.println(command);
  
  // Check if it's a JSON command
  if (command.startsWith("{")) {
    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, command);
    
    if (error) {
      Serial.print("JSON parsing failed: ");
      Serial.println(error.c_str());
      return;
    }
    
    // Check for command field (could be "command" or "action")
    const char* action = NULL;
    if (doc.containsKey("command")) {
      action = doc["command"];
    } else if (doc.containsKey("action")) {
      action = doc["action"];
    }
    
    if (action && strcmp(action, "pump") == 0) {
      int pin = doc["pin"];
      long duration = doc["duration"];
      
      Serial.print("Activating pump on pin ");
      Serial.print(pin);
      Serial.print(" for ");
      Serial.print(duration);
      Serial.println("ms");
      
      // Activate the pin
      pinMode(pin, OUTPUT);
      digitalWrite(pin, HIGH);
      delay(duration);
      digitalWrite(pin, LOW);
      
      Serial.println("Pump activation complete");
    }
  } 
  // Check if it's a simple text command like PUMP:27:500
  else if (command.startsWith("PUMP:") || command.startsWith("DOSING:")) {
    int firstColon = command.indexOf(':');
    int secondColon = command.indexOf(':', firstColon + 1);
    
    if (firstColon > 0 && secondColon > 0) {
      int pin = command.substring(firstColon + 1, secondColon).toInt();
      long duration = command.substring(secondColon + 1).toInt();
      
      Serial.print("Activating pump on pin ");
      Serial.print(pin);
      Serial.print(" for ");
      Serial.print(duration);
      Serial.println("ms");
      
      // Activate the pin
      pinMode(pin, OUTPUT);
      digitalWrite(pin, HIGH);
      delay(duration);
      digitalWrite(pin, LOW);
      
      Serial.println("Pump activation complete");
    }
  }
  // Check for other command formats
  else if (command.startsWith("ACTIVATE_PUMP")) {
    // Parse the simple text command
    int firstSpace = command.indexOf(' ');
    int secondSpace = command.indexOf(' ', firstSpace + 1);
    
    if (firstSpace > 0 && secondSpace > 0) {
      int pin = command.substring(firstSpace + 1, secondSpace).toInt();
      long duration = command.substring(secondSpace + 1).toInt();
      
      Serial.print("Activating pump on pin ");
      Serial.print(pin);
      Serial.print(" for ");
      Serial.print(duration);
      Serial.println("ms");
      
      // Activate the pin
      pinMode(pin, OUTPUT);
      digitalWrite(pin, HIGH);
      delay(duration);
      digitalWrite(pin, LOW);
      
      Serial.println("Pump activation complete");
    }
  }
}

// Add this to your setup() function
void setup() {
  // ...existing setup code...
  
  // Configure pump pins
  pinMode(PH_PLUS_PIN, OUTPUT);
  pinMode(PH_MINUS_PIN, OUTPUT);
  pinMode(EC_PLUS_PIN, OUTPUT);
  digitalWrite(PH_PLUS_PIN, LOW);
  digitalWrite(PH_MINUS_PIN, LOW);
  digitalWrite(EC_PLUS_PIN, LOW);
}

// Add this to your loop() function
void loop() {
  // ...existing loop code...
  
  // Check for dosing commands
  if (Serial.available()) {
    String command = Serial.readStringUntil('\\n');
    command.trim();
    handleDosingCommand(command);
  }
}
"""
        logger.info("Generated ESP32 code for handling dosing commands:")
        logger.info(esp32_code)
        
        # Save the code to a file
        with open("esp32_pump_handler.cpp", "w") as f:
            f.write(esp32_code)
        logger.info("ESP32 code saved to esp32_pump_handler.cpp")
    
    def generate_dashboard_bridge(self):
        """Generate code to add to the dashboard to bridge ZMQ and serial"""
        bridge_code = """
# Add this to your dashboard.py file

import serial
import zmq
import json
import threading
import time

# Configuration
SERIAL_PORT = '/dev/cu.usbserial-110'
BAUD_RATE = 115200
ZMQ_SERVER = "tcp://*:5555"  # Bind to all interfaces

# Initialize serial connection
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # Allow time for serial connection to stabilize
    print(f"Serial connection established on {SERIAL_PORT}")
except Exception as e:
    print(f"Failed to establish serial connection: {e}")
    ser = None

# Initialize ZMQ
context = zmq.Context()
socket = context.socket(zmq.REP)
socket.bind(ZMQ_SERVER)
print(f"ZMQ server started on {ZMQ_SERVER}")

def handle_zmq_to_serial():
    while True:
        try:
            # Wait for next request from client
            message = socket.recv_string()
            print(f"Received ZMQ message: {message}")
            
            if ser is None:
                socket.send_string(json.dumps({
                    "success": False,
                    "error": "Serial connection not available"
                }))
                continue
                
            try:
                # Check if it's already a JSON string
                json_data = json.loads(message)
                message = json.dumps(json_data)
            except json.JSONDecodeError:
                # It's not JSON, format as simple command
                if ":" in message:
                    # Already formatted as PUMP:PIN:DURATION
                    message = message
                else:
                    # Unknown format
                    socket.send_string(json.dumps({
                        "success": False,
                        "error": "Invalid command format"
                    }))
                    continue
            
            # Forward message to serial with newline
            ser.write((message + "\\n").encode())
            
            # Read response from serial (if any)
            time.sleep(0.5)  # Wait for response
            serial_response = ser.read_all().decode('utf-8', errors='ignore')
            
            if serial_response:
                socket.send_string(json.dumps({
                    "success": True,
                    "message": "Command sent to ESP32",
                    "response": serial_response
                }))
            else:
                socket.send_string(json.dumps({
                    "success": True,
                    "message": "Command sent to ESP32, no response received"
                }))
                
        except Exception as e:
            print(f"Error in ZMQ thread: {e}")
            socket.send_string(json.dumps({
                "success": False,
                "error": str(e)
            }))

# Start ZMQ handler in a separate thread
zmq_thread = threading.Thread(target=handle_zmq_to_serial)
zmq_thread.daemon = True
zmq_thread.start()
"""
        logger.info("Generated dashboard bridge code:")
        logger.info(bridge_code)
        
        # Save the code to a file
        with open("dashboard_bridge_code.py", "w") as f:
            f.write(bridge_code)
        logger.info("Dashboard bridge code saved to dashboard_bridge_code.py")
    
    def run_pump_test(self):
        """Run a direct pump test"""
        if not self.serial_conn:
            logger.error("Serial connection not available")
            return
            
        for pump_name, pin in [("pH Plus", PIN_PH_PLUS), ("pH Minus", PIN_PH_MINUS), ("EC", PIN_EC)]:
            logger.info(f"Testing {pump_name} pump on pin {pin}")
            
            # Direct digitalWrite commands
            on_cmd = f"DIGITALWRITE:{pin}:1\n"
            off_cmd = f"DIGITALWRITE:{pin}:0\n"
            
            try:
                # Turn on
                logger.info(f"Turning on pin {pin}")
                self.serial_conn.write(on_cmd.encode())
                time.sleep(1)  # Run for 1 second
                
                # Turn off
                logger.info(f"Turning off pin {pin}")
                self.serial_conn.write(off_cmd.encode())
                
                # Check for response
                time.sleep(0.5)
                response = self.serial_conn.read_all().decode('utf-8', errors='ignore')
                if response:
                    logger.info(f"Received response: {response}")
                else:
                    logger.info("No response received")
            except Exception as e:
                logger.error(f"Error testing {pump_name} pump: {e}")
    
    def run(self):
        """Run the improved pump control tool"""
        if not self.setup():
            logger.error("Setup failed, cannot continue")
            return
        
        # Test various command formats
        logger.info("\n" + "="*20 + " TESTING COMMAND FORMATS " + "="*20)
        for pump_name, pin in [("pH Plus", PIN_PH_PLUS), ("pH Minus", PIN_PH_MINUS), ("EC", PIN_EC)]:
            logger.info(f"\nTesting {pump_name} pump (pin {pin}):")
            self.test_format_variations(pin, 500)  # 500ms test duration
        
        # Run direct pump test
        logger.info("\n" + "="*20 + " TESTING DIRECT PUMP CONTROL " + "="*20)
        self.run_pump_test()
        
        # Generate ESP32 code
        logger.info("\n" + "="*20 + " GENERATING ESP32 CODE " + "="*20)
        self.generate_esp32_code()
        
        # Generate dashboard bridge code
        logger.info("\n" + "="*20 + " GENERATING DASHBOARD BRIDGE CODE " + "="*20)
        self.generate_dashboard_bridge()
        
        # Final recommendations
        logger.info("\n" + "="*20 + " RECOMMENDATIONS " + "="*20)
        logger.info("1. Add the ESP32 code to your main.cpp file")
        logger.info("2. Add the dashboard bridge code to your dashboard.py file")
        logger.info("3. Test the connection using the simplest command format that works")
        logger.info("4. Make sure the ESP32 is correctly parsing the commands")
        logger.info("5. Ensure the dashboard forwards ZMQ messages to the serial connection")
        
if __name__ == "__main__":
    tool = ImprovedPumpControl()
    tool.run()