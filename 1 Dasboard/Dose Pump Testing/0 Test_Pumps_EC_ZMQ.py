#!/usr/bin/env python3
"""
Test script for EC pump on pin 25 using ZMQ with detailed logging
"""
import zmq
import time
import sys
import logging
import json

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pump_test_zmq.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("PumpTest")

# Get duration from command line argument or prompt user
if len(sys.argv) > 1:
    try:
        duration_seconds = float(sys.argv[1])
    except ValueError:
        logger.error("Invalid duration. Please enter a number in seconds.")
        sys.exit(1)
else:
    try:
        duration_seconds = float(input("Enter pump duration in seconds: "))
    except ValueError:
        logger.warning("Invalid input. Using default duration of 10 seconds.")
        duration_seconds = 10.0

# Convert to milliseconds for the ESP32
duration_ms = int(duration_seconds * 1000)

# Ensure only that duration is positive
if duration_seconds <= 0:
    logger.warning("Duration must be greater than 0. Using 0.5 seconds.")
    duration_seconds = 0.5
    duration_ms = 500

logger.info(f"Running EC pump for {duration_seconds:.1f} seconds ({duration_ms} ms)...")

# Setup ZMQ connection
context = zmq.Context()
socket = context.socket(zmq.REQ)
try:
    # Connect to ZMQ server
    logger.info("Connecting to ZMQ server on tcp://localhost:5555...")
    socket.connect("tcp://localhost:5555")
    socket.RCVTIMEO = 5000  # Set timeout to 5 seconds

    # Create command for EC pump
    command = {
        'action': 'dose',
        'pin': 25,
        'duration_ms': duration_ms,
        'pump_type': 'ec_plus'
    }
    
    logger.info(f"Sending command: {json.dumps(command)}")
    
    # Send command
    socket.send_json(command)
    logger.info("Command sent. Waiting for response...")
    
    try:
        # Wait for response
        response = socket.recv_json()
        logger.info(f"Response received: {json.dumps(response)}")
        
        if response.get('success'):
            logger.info("SUCCESS: EC pump activation command accepted")
        else:
            logger.error(f"FAILED: EC pump activation failed: {response.get('error', 'Unknown error')}")
    
    except zmq.error.Again:
        logger.error("TIMEOUT: No response received from ZMQ server")
    
    # Monitor for the duration of the pump operation
    logger.info(f"Monitoring pump operation for {duration_seconds + 5:.1f} seconds...")
    
    # Create empty status request
    status_request = {'action': 'status'}
    
    # Monitor for duration + 5 seconds
    start_time = time.time()
    while time.time() - start_time < duration_seconds + 5:
        time.sleep(1)  # Check status every second
        
        try:
            # Request pump status
            socket.send_json(status_request)
            status = socket.recv_json()
            logger.info(f"Status update: {json.dumps(status)}")
            
            # Check if the pin is active (may need to adjust based on actual status format)
            if 'pins' in status and 25 in status['pins']:
                logger.info(f"Pin 25 state: {status['pins'][25]}")
            elif 'active_pins' in status:
                logger.info(f"Active pins: {status['active_pins']}")
            
        except zmq.error.Again:
            logger.warning("Status update request timed out")
        except Exception as e:
            logger.error(f"Error during status check: {str(e)}")
    
    logger.info("EC pump test complete")

except zmq.error.ZMQError as e:
    logger.error(f"ZMQ Error: {str(e)}")
except KeyboardInterrupt:
    logger.info("\nTest interrupted by user.")
    # Try to send stop command if interrupted
    try:
        stop_command = {
            'action': 'stop',
            'pin': 25
        }
        socket.send_json(stop_command)
        logger.info("Sent stop command to pump.")
        response = socket.recv_json()
        logger.info(f"Stop command response: {json.dumps(response)}")
    except Exception as e:
        logger.error(f"Error sending stop command: {str(e)}")
finally:
    # Clean up
    socket.close()
    context.term()
    logger.info("ZMQ connection closed")