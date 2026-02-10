#!/usr/bin/env python3
"""
Advanced Pump Diagnostics Tool

This tool systematically tests both direct serial communication and ZMQ
communication to identify where the pump control communication is failing.
"""

import serial
import time
import json
import logging
import os
import sys
import zmq
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pump_diagnostics.log"),
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

class PumpDiagnosticTool:
    def __init__(self):
        self.serial_conn = None
        self.zmq_socket = None
        
    def setup(self):
        """Initialize connections"""
        logger.info("Starting pump diagnostic tool...")
        
        # Try to establish serial connection
        try:
            self.serial_conn = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)  # Allow time for serial connection to stabilize
            logger.info(f"Serial connection established on {SERIAL_PORT}")
        except Exception as e:
            logger.error(f"Failed to establish serial connection: {e}")
            self.serial_conn = None
        
        # Try to establish ZMQ connection
        try:
            context = zmq.Context()
            self.zmq_socket = context.socket(zmq.REQ)
            self.zmq_socket.connect(ZMQ_SERVER)
            self.zmq_socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout
            logger.info(f"ZMQ connection established to {ZMQ_SERVER}")
        except Exception as e:
            logger.error(f"Failed to establish ZMQ connection: {e}")
            self.zmq_socket = None
    
    def test_direct_serial(self, pin, duration_ms):
        """Test direct serial communication to control pump"""
        if not self.serial_conn:
            logger.error("Serial connection not available")
            return False
            
        try:
            # Format 1: Try simple command
            cmd = f"PUMP:{pin}:{duration_ms}\n"
            logger.info(f"Sending direct serial command: {cmd.strip()}")
            self.serial_conn.write(cmd.encode())
            
            # Read response
            time.sleep(0.5)
            response = self.serial_conn.read_all().decode('utf-8', errors='ignore')
            logger.info(f"Direct serial response: {response}")
            
            # Format 2: Try JSON format
            cmd_json = json.dumps({"command": "pump", "pin": pin, "duration": duration_ms}) + "\n"
            logger.info(f"Sending direct serial JSON command: {cmd_json.strip()}")
            self.serial_conn.write(cmd_json.encode())
            
            # Read response
            time.sleep(0.5)
            response = self.serial_conn.read_all().decode('utf-8', errors='ignore')
            logger.info(f"Direct serial JSON response: {response}")
            
            return True
        except Exception as e:
            logger.error(f"Error in direct serial test: {e}")
            return False
    
    def test_zmq(self, pin, duration_ms):
        """Test ZMQ communication to control pump"""
        if not self.zmq_socket:
            logger.error("ZMQ connection not available")
            return False
            
        try:
            # Format 1: Try simple command
            cmd = f"PUMP:{pin}:{duration_ms}"
            logger.info(f"Sending ZMQ command: {cmd}")
            self.zmq_socket.send_string(cmd)
            
            # Read response
            try:
                response = self.zmq_socket.recv_string()
                logger.info(f"ZMQ response: {response}")
            except zmq.error.Again:
                logger.error("ZMQ response timeout")
            
            # Format 2: Try JSON format
            cmd_json = json.dumps({"command": "pump", "pin": pin, "duration": duration_ms})
            logger.info(f"Sending ZMQ JSON command: {cmd_json}")
            self.zmq_socket.send_string(cmd_json)
            
            # Read response
            try:
                response = self.zmq_socket.recv_string()
                logger.info(f"ZMQ JSON response: {response}")
            except zmq.error.Again:
                logger.error("ZMQ JSON response timeout")
            
            return True
        except Exception as e:
            logger.error(f"Error in ZMQ test: {e}")
            return False
    
    def extract_main_cpp_handler(self):
        """Try to extract and analyze the command handler in main.cpp"""
        try:
            main_cpp_path = "../src/main.cpp"
            if os.path.exists(main_cpp_path):
                with open(main_cpp_path, 'r') as f:
                    content = f.read()
                    
                # Look for handleDosingCommand function
                if "handleDosingCommand" in content:
                    index = content.find("handleDosingCommand")
                    start_index = content.rfind("\n", 0, index)
                    end_index = content.find("}", index)
                    if end_index > start_index:
                        handler_code = content[start_index:end_index+1]
                        logger.info(f"Found command handler in main.cpp:\n{handler_code}")
                    else:
                        logger.warning("Could not extract command handler code")
                else:
                    logger.warning("handleDosingCommand function not found in main.cpp")
            else:
                logger.warning(f"Could not find main.cpp at {main_cpp_path}")
        except Exception as e:
            logger.error(f"Error extracting main.cpp handler: {e}")
    
    def analyze_zmq_flow(self):
        """Analyze ZMQ message flow between components"""
        # Check dashboard code for ZMQ message handling
        try:
            dashboard_path = "1p2 dashboard v7p2.py"
            if os.path.exists(dashboard_path):
                with open(dashboard_path, 'r') as f:
                    content = f.read()
                    
                # Look for ZMQ message handling
                if "zmq.REP" in content:
                    logger.info("Dashboard is using ZMQ REP socket for responding to requests")
                if "@app.callback" in content and "zmq" in content:
                    logger.info("Dashboard appears to have ZMQ callbacks")
                
                # Check for serial forwarding logic
                if "serial.write" in content and "zmq" in content:
                    logger.info("Dashboard has code to forward ZMQ messages to serial")
                else:
                    logger.warning("Could not find code to forward ZMQ messages to serial in dashboard")
            else:
                logger.warning(f"Could not find dashboard at {dashboard_path}")
        except Exception as e:
            logger.error(f"Error analyzing ZMQ flow: {e}")
    
    def run_comprehensive_tests(self):
        """Run a comprehensive series of tests to diagnose the issue"""
        logger.info("="*50)
        logger.info("RUNNING COMPREHENSIVE PUMP DIAGNOSTICS")
        logger.info("="*50)
        
        # Setup connections
        self.setup()
        
        # Extract and analyze command handlers
        logger.info("\n" + "="*20 + " ANALYZING CODE " + "="*20)
        self.extract_main_cpp_handler()
        self.analyze_zmq_flow()
        
        # Test each pump with each method
        for pump_name, pin in [("pH Plus", PIN_PH_PLUS), ("pH Minus", PIN_PH_MINUS), ("EC", PIN_EC)]:
            logger.info("\n" + "="*20 + f" TESTING {pump_name} PUMP (PIN {pin}) " + "="*20)
            
            # Test with direct serial
            logger.info("\n>> Testing direct serial communication")
            self.test_direct_serial(pin, 500)  # Short 500ms test
            
            # Test with ZMQ
            logger.info("\n>> Testing ZMQ communication")
            self.test_zmq(pin, 500)  # Short 500ms test
            
        # Provide diagnosis
        logger.info("\n" + "="*20 + " DIAGNOSIS " + "="*20)
        logger.info("1. Check if responses were received for both serial and ZMQ tests")
        logger.info("2. Compare the command formats with what the ESP32 expects")
        logger.info("3. Verify that the dashboard is forwarding ZMQ messages to serial")
        logger.info("4. Confirm that handleDosingCommand in main.cpp correctly parses commands")
        
        # Cleanup
        if self.serial_conn:
            self.serial_conn.close()
        logger.info("\nDiagnostics complete. Check pump_diagnostics.log for detailed results.")

if __name__ == "__main__":
    tool = PumpDiagnosticTool()
    tool.run_comprehensive_tests()