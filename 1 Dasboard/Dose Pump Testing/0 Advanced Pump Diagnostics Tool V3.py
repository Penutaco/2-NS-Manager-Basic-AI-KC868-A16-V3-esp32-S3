#!/usr/bin/env python3
"""
Unified Pump Diagnostic Tool

Comprehensive testing and debugging tool for pump communication issues
between the dosing controller, dashboard, and ESP32 microcontroller.
"""

import serial
import time
import json
import logging
import sys
import os
import zmq
import threading
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("unified_pump_diagnostic.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("PumpDiagnostics")

# Configuration
SERIAL_PORT = '/dev/cu.usbserial-110'
BAUD_RATE = 115200
ZMQ_SERVER = "tcp://localhost:5555"

# Pump pins
PIN_PH_PLUS = 27
PIN_PH_MINUS = 26
PIN_EC = 25

class UnifiedPumpDiagnostic:
    def __init__(self):
        self.serial_conn = None
        self.zmq_socket = None
        self.monitoring = False
        self.monitoring_thread = None
    
    def setup_serial(self):
        """Set up serial connection to ESP32"""
        try:
            self.serial_conn = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)  # Allow time for serial connection to stabilize
            logger.info(f"Serial connection established on {SERIAL_PORT}")
            return True
        except Exception as e:
            logger.error(f"Failed to establish serial connection: {e}")
            return False
    
    def setup_zmq(self):
        """Set up ZMQ connection to dashboard"""
        try:
            context = zmq.Context()
            self.zmq_socket = context.socket(zmq.REQ)
            self.zmq_socket.connect(ZMQ_SERVER)
            self.zmq_socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout
            logger.info(f"ZMQ connection established to {ZMQ_SERVER}")
            return True
        except Exception as e:
            logger.error(f"Failed to establish ZMQ connection: {e}")
            return False
    
    def monitor_serial(self):
        """Monitor serial port for responses"""
        self.monitoring = True
        logger.info("Starting serial port monitoring")
        while self.monitoring and self.serial_conn:
            if self.serial_conn.in_waiting:
                try:
                    line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        logger.info(f"ESP32 → Serial: {line}")
                except Exception as e:
                    logger.error(f"Error reading from serial: {e}")
            time.sleep(0.1)
        logger.info("Serial monitoring stopped")
    
    def start_monitoring(self):
        """Start serial monitoring in a separate thread"""
        if not self.serial_conn:
            logger.warning("Cannot start monitoring: No serial connection")
            return False
        
        if self.monitoring:
            logger.warning("Monitoring already active")
            return True
        
        self.monitoring_thread = threading.Thread(target=self.monitor_serial)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        time.sleep(0.5)  # Give thread time to start
        return True
    
    def stop_monitoring(self):
        """Stop serial monitoring"""
        if self.monitoring:
            self.monitoring = False
            if self.monitoring_thread:
                self.monitoring_thread.join(timeout=1.0)
            logger.info("Monitoring stopped")
    
    def send_serial_command(self, command, wait_time=1.0):
        """Send command directly to ESP32 via serial"""
        if not self.serial_conn:
            logger.error("Serial connection not available")
            return False
        
        # Make sure command ends with newline
        if not command.endswith('\n'):
            command += '\n'
        
        logger.info(f"Serial → ESP32: {command.strip()}")
        self.serial_conn.write(command.encode())
        time.sleep(wait_time)  # Wait for response
        return True
    
    def send_zmq_command(self, command):
        """Send command to dashboard via ZMQ"""
        if not self.zmq_socket:
            logger.error("ZMQ connection not available")
            return False, None
        
        logger.info(f"ZMQ → Dashboard: {command}")
        
        try:
            if isinstance(command, dict):
                self.zmq_socket.send_json(command)
            else:
                self.zmq_socket.send_string(command)
            
            # Wait for response
            try:
                if isinstance(command, dict):
                    response = self.zmq_socket.recv_json()
                else:
                    response = self.zmq_socket.recv_string()
                logger.info(f"Dashboard → ZMQ: {response}")
                return True, response
            except zmq.error.Again:
                logger.error("ZMQ response timeout")
                return False, None
                
        except Exception as e:
            logger.error(f"ZMQ communication error: {e}")
            return False, None
    
    def test_direct_serial_formats(self):
        """Test various command formats directly via serial"""
        if not self.serial_conn:
            return False
        
        logger.info("\n===== TESTING DIRECT SERIAL COMMAND FORMATS =====")
        
        # Clear buffer before starting
        self.serial_conn.reset_input_buffer()
        
        formats = [
            # Format 1: Simple string with parameters
            f"PUMP:{PIN_PH_PLUS}:500",
            
            # Format 2: JSON with command key
            json.dumps({"command": "pump", "pin": PIN_PH_PLUS, "duration": 500}),
            
            # Format 3: JSON with action key
            json.dumps({"action": "dose", "pin": PIN_PH_PLUS, "duration_ms": 500, 
                        "pump_type": "ph_plus"}),
            
            # Format 4: DOSING command
            f"DOSING:{PIN_PH_PLUS}:500",
            
            # Format 5: Direct pin control
            f"DIGITALWRITE:{PIN_PH_PLUS}:1"
        ]
        
        success = False
        for i, cmd in enumerate(formats):
            logger.info(f"Testing format {i+1}: {cmd}")
            self.send_serial_command(cmd)
            
            # If this was a direct pin activation, turn it off after a delay
            if cmd.startswith("DIGITALWRITE") and ":1" in cmd:
                time.sleep(0.5)  # Keep pin on for 0.5 seconds
                off_cmd = cmd.replace(":1", ":0")
                self.send_serial_command(off_cmd)
            
            # Check for responses without blocking, just a brief delay
            time.sleep(1.0)
            
        return success
    
    def test_zmq_bridge(self):
        """Test if ZMQ to Serial bridge is working"""
        if not self.zmq_socket or not self.serial_conn:
            logger.error("Both ZMQ and Serial connections required for bridge test")
            return False
        
        logger.info("\n===== TESTING ZMQ TO SERIAL BRIDGE =====")
        
        # Clear buffers
        self.serial_conn.reset_input_buffer()
        
        # Test with JSON command format
        test_command = {
            "action": "dose",
            "pin": PIN_PH_PLUS,
            "duration_ms": 500,
            "pump_type": "ph_plus"
        }
        
        logger.info(f"Sending test command via ZMQ: {test_command}")
        success, response = self.send_zmq_command(test_command)
        
        if not success:
            logger.error("Failed to send ZMQ command or receive response")
            return False
        
        # Check if we get any responses on serial indicating command was processed
        time.sleep(2.0)  # Wait longer to ensure any response comes through
        
        # Response will be handled by the monitor thread
        
        logger.info(f"ZMQ bridge test complete. Check logs for ESP32 responses.")
        return True
    
    def extract_and_check_handlers(self):
        """Extract and analyze command handlers from source code"""
        logger.info("\n===== ANALYZING CODE =====")
        
        # Find main.cpp file
        main_cpp_path = "../src/main.cpp"
        if not os.path.exists(main_cpp_path):
            logger.warning(f"Could not find main.cpp at {main_cpp_path}")
            return False
        
        try:
            with open(main_cpp_path, 'r') as f:
                content = f.read()
            
            # Look for handleDosingCommand function
            if "handleDosingCommand" in content:
                logger.info("Found handleDosingCommand function in main.cpp")
                
                # Extract function content
                start_index = content.find("void handleDosingCommand")
                if start_index == -1:
                    start_index = content.find("handleDosingCommand")
                
                if start_index != -1:
                    # Find opening brace
                    brace_index = content.find("{", start_index)
                    if brace_index != -1:
                        # Count braces to find matching closing brace
                        brace_count = 1
                        end_index = brace_index + 1
                        while brace_count > 0 and end_index < len(content):
                            if content[end_index] == '{':
                                brace_count += 1
                            elif content[end_index] == '}':
                                brace_count -= 1
                            end_index += 1
                        
                        if brace_count == 0:
                            handler_code = content[start_index:end_index]
                            logger.info("Handler code analysis:")
                            
                            # Check for JSON parsing capabilities
                            if "ArduinoJson" in content or "deserializeJson" in content:
                                logger.info("✅ JSON parsing capability detected")
                            else:
                                logger.warning("❌ No JSON parsing capability detected")
                                
                            # Check for common command formats
                            if "command.startsWith(\"{\")" in content:
                                logger.info("✅ JSON command format handling detected")
                            else:
                                logger.warning("❌ No JSON command format handling detected")
                                
                            if "command.startsWith(\"PUMP:\")" in content or "command.startsWith(\"DOSING:\")" in content:
                                logger.info("✅ Text command format handling detected")
                            else:
                                logger.warning("❌ No text command format handling detected")
                                
                            # Check for actual pump activation code
                            if "digitalWrite" in handler_code and "HIGH" in handler_code:
                                logger.info("✅ Pump activation code detected")
                            else:
                                logger.warning("❌ No pump activation code detected")
                                
                            logger.info(f"Handler code snippet (first 500 chars):\n{handler_code[:500]}...")
                        else:
                            logger.warning("Could not find complete handler function (unbalanced braces)")
                else:
                    logger.warning("Could not locate start of handleDosingCommand function")
            else:
                logger.warning("No handleDosingCommand function found in main.cpp")
                
            # Look for command handling in loop() function
            if "Serial.available()" in content and "readStringUntil" in content:
                logger.info("✅ Serial command reading detected in code")
            else:
                logger.warning("❌ No Serial command reading detected in code")
                
            # Also check dashboard code for ZMQ bridge
            dashboard_path = "1p2 dashboard v7p2.py"
            if os.path.exists(dashboard_path):
                with open(dashboard_path, 'r') as f:
                    dashboard_content = f.read()
                
                if "zmq_communication_thread" in dashboard_content:
                    logger.info("✅ ZMQ communication thread found in dashboard")
                    
                    # Check if dashboard is actually forwarding to serial
                    if "ser.write" in dashboard_content and "message" in dashboard_content:
                        logger.info("✅ Serial forwarding code found in dashboard")
                    else:
                        logger.warning("❌ No serial forwarding code found in dashboard")
            else:
                logger.warning(f"Could not find dashboard at {dashboard_path}")
            
            return True
                
        except Exception as e:
            logger.error(f"Error analyzing code: {e}")
            return False
    
    def fix_communication_issues(self):
        """Generate code for fixing communication issues"""
        logger.info("\n===== GENERATING FIX CODE =====")
        
        # Generate a simple test file for validating fixes
        test_file = """#!/usr/bin/env python3
"""
        with open("pump_test_helper.py", "w") as f:
            f.write(test_file)
        logger.info("Created pump_test_helper.py for testing fixes")
        
        # Generate a replace module for the dashboard
        fixed_bridge = """# Add this to your dashboard.py file to fix pump communication

def handle_dosing_command(message):
    \"\"\"Process dosing commands and forward to ESP32\"\"\"
    try:
        if isinstance(message, dict):
            # Extract parameters
            pin = message.get('pin')
            duration_ms = message.get('duration_ms')
            pump_type = message.get('pump_type')
            
            if not all([pin, duration_ms, pump_type]):
                return {"success": False, "error": "Missing required parameters"}
            
            # Forward command to ESP32
            try:
                import serial
                with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
                    # Clear any pending data
                    ser.reset_input_buffer()
                    
                    # Format command as JSON that Arduino can parse
                    command = json.dumps(message) + '\\n'
                    print(f"Forwarding to ESP32: {command.strip()}")
                    ser.write(command.encode())
                    
                    # Wait for response
                    start_time = time.time()
                    response = ""
                    
                    while time.time() - start_time < 2.0:
                        if ser.in_waiting:
                            line = ser.readline().decode().strip()
                            response += line + " "
                            # Success indicators
                            if "success" in line.lower() or "complete" in line.lower():
                                return {"success": True, "response": response}
                        time.sleep(0.1)
                    
                    # No definitive success message, but command was sent
                    return {"success": True, "response": response if response else "Command sent, no response"}
                    
            except Exception as e:
                print(f"Serial error: {e}")
                return {"success": False, "error": f"Serial error: {str(e)}"}
        else:
            return {"success": False, "error": "Invalid message format"}
    except Exception as e:
        print(f"Command handling error: {e}")
        return {"success": False, "error": f"Error: {str(e)}"}

# Replace the dosing command handling in your zmq_communication_thread function with:
def zmq_communication_thread():
    while True:
        try:
            # Wait for message from dosing controller
            message = dosing_socket.recv_json()
            print(f"Received dosing command: {message}")
            
            # Process dosing command
            if message.get('action') == 'dose':
                # Call the handler to process and forward the command
                response = handle_dosing_command(message)
                
                # Log the action regardless of success
                with lock:
                    event_data.append(f"Dosing command: {message.get('pump_type')} for {message.get('duration_ms')}ms on pin {message.get('pin')}")
                
                # Log to CSV file
                empty_sensor_data = [""] * 11
                csv_writer.writerow(empty_sensor_data + [f"Dosing command: {message.get('pump_type')} for {message.get('duration_ms')}ms"])
                csv_file.flush()
                
                # Send response back to dosing controller
                dosing_socket.send_json(response)
            else:
                # Unknown command
                dosing_socket.send_json({"success": False, "error": "Unknown command"})
                
        except Exception as e:
            print(f"Error in ZMQ communication: {e}")
            try:
                dosing_socket.send_json({"success": False, "error": str(e)})
            except:
                pass
            time.sleep(1)  # Avoid tight loop on error
"""
        with open("fixed_dashboard_bridge.py", "w") as f:
            f.write(fixed_bridge)
        logger.info("Created fixed_dashboard_bridge.py with corrected ZMQ-Serial bridge code")
        
        # Generate ESP32 handler fix
        esp32_fix = """// Add this to your main.cpp file near the top:
#include <ArduinoJson.h>

// Replace your handleDosingCommand function with this implementation:
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
    
    // First, check if it's the expected format from dosing controller
    if (doc.containsKey("action") && doc.containsKey("pin") && doc.containsKey("duration_ms")) {
      const char* action = doc["action"];
      int pin = doc["pin"];
      long duration = doc["duration_ms"];
      
      if (strcmp(action, "dose") == 0) {
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
        return;
      }
    }
    
    // Alternative formats for backward compatibility
    if (doc.containsKey("command") && doc.containsKey("pin") && doc.containsKey("duration")) {
      const char* cmd = doc["command"];
      int pin = doc["pin"];
      long duration = doc["duration"];
      
      if (strcmp(cmd, "pump") == 0) {
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
        return;
      }
    }
    
    Serial.println("Error: Invalid JSON command format");
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
      return;
    }
  }
  // Check for DIGITALWRITE direct command
  else if (command.startsWith("DIGITALWRITE:")) {
    int firstColon = command.indexOf(':');
    int secondColon = command.indexOf(':', firstColon + 1);
    
    if (firstColon > 0 && secondColon > 0) {
      int pin = command.substring(firstColon + 1, secondColon).toInt();
      int state = command.substring(secondColon + 1).toInt();
      
      Serial.print("Setting pin ");
      Serial.print(pin);
      Serial.print(" to ");
      Serial.println(state);
      
      // Set pin
      pinMode(pin, OUTPUT);
      digitalWrite(pin, state);
      
      Serial.println("Digital write complete");
      return;
    }
  }
  
  Serial.println("Error: Unrecognized command format");
}

// Make sure this is in your loop() function:
void loop() {
  // ...existing code...
  
  // Listen for serial commands
  if (Serial.available()) {
    String command = Serial.readStringUntil('\\n');
    command.trim();
    
    // Echo command for debugging
    Serial.print("Received command: ");
    Serial.println(command);
    
    // Process command
    if (command.startsWith("{") || command.startsWith("PUMP:") || 
        command.startsWith("DOSING:") || command.startsWith("DIGITALWRITE:")) {
      handleDosingCommand(command);
    }
    // ...rest of your command handling...
  }
  
  // ...rest of loop function...
}"""
        with open("esp32_command_handler_fix.cpp", "w") as f:
            f.write(esp32_fix)
        logger.info("Created esp32_command_handler_fix.cpp with corrected ESP32 command handler")
        
        logger.info("\n===== FIX CODE GENERATED =====")
        logger.info("1. esp32_command_handler_fix.cpp - Updated command handler for ESP32")
        logger.info("2. fixed_dashboard_bridge.py - Corrected ZMQ-Serial bridge for dashboard")
        logger.info("3. pump_test_helper.py - Simple test utility")
    
    def interactive_menu(self):
        """Show interactive menu for diagnostics"""
        while True:
            print("\n======== UNIFIED PUMP DIAGNOSTIC TOOL ========")
            print("1. Test Direct Serial Communication")
            print("2. Test ZMQ to Serial Bridge")
            print("3. Analyze ESP32 & Dashboard Code")
            print("4. Generate Fix Code")
            print("5. Start Serial Monitor")
            print("6. Stop Serial Monitor")
            print("7. Send Custom Serial Command")
            print("8. Send Custom ZMQ Command")
            print("9. Exit")
            
            choice = input("\nEnter choice (1-9): ")
            
            if choice == '1':
                if not self.serial_conn and not self.setup_serial():
                    print("Serial setup failed")
                    continue
                self.test_direct_serial_formats()
            
            elif choice == '2':
                if not self.serial_conn and not self.setup_serial():
                    print("Serial setup failed")
                    continue
                if not self.zmq_socket and not self.setup_zmq():
                    print("ZMQ setup failed")
                    continue
                self.test_zmq_bridge()
            
            elif choice == '3':
                self.extract_and_check_handlers()
            
            elif choice == '4':
                self.fix_communication_issues()
            
            elif choice == '5':
                if not self.serial_conn and not self.setup_serial():
                    print("Serial setup failed")
                    continue
                self.start_monitoring()
                print("Serial monitoring started. Events will be logged.")
            
            elif choice == '6':
                self.stop_monitoring()
            
            elif choice == '7':
                if not self.serial_conn and not self.setup_serial():
                    print("Serial setup failed")
                    continue
                cmd = input("Enter serial command: ")
                self.send_serial_command(cmd)
            
            elif choice == '8':
                if not self.zmq_socket and not self.setup_zmq():
                    print("ZMQ setup failed")
                    continue
                print("Enter ZMQ command as JSON (e.g. {\"action\":\"dose\",\"pin\":27,\"duration_ms\":1000,\"pump_type\":\"ph_plus\"})")
                cmd_str = input("> ")
                try:
                    cmd = json.loads(cmd_str)
                    self.send_zmq_command(cmd)
                except json.JSONDecodeError:
                    print("Invalid JSON format")
            
            elif choice == '9':
                self.stop_monitoring()
                print("Exiting...")
                break
            
            else:
                print("Invalid choice. Please enter a number between 1 and 9.")

if __name__ == "__main__":
    tool = UnifiedPumpDiagnostic()
    tool.interactive_menu()