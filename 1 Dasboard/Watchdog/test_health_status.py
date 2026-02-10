#!/usr/bin/env python3
"""
Test health status file creation
"""

import os
import json
from datetime import datetime

# Mimic the dashboard's health status variables
last_data_received = datetime.now()
connection_healthy = False
current_serial_port = '/dev/ttyUSB0'
reconnection_in_progress = False
health_monitor_active = True
connection_status_log = ['[16:30:00] INFO: Starting health check test']

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

def write_health_status():
    """Write current health status to JSON file for watchdog monitoring"""
    try:
        health_data = {
            'last_update': datetime.now().isoformat(),
            'connection_healthy': connection_healthy,
            'last_data_received': last_data_received.isoformat() if last_data_received else None,
            'current_port': current_serial_port,
            'reconnection_in_progress': reconnection_in_progress,
            'health_monitor_active': health_monitor_active,
            'recent_errors': connection_status_log[-5:] if connection_status_log else []  # Last 5 log entries
        }
        
        health_file_path = os.path.join(DATA_DIR, 'dashboard_health.json')
        with open(health_file_path, 'w') as f:
            json.dump(health_data, f, indent=2)
        
        print(f"✅ Health status file created: {health_file_path}")
        return health_file_path
            
    except Exception as e:
        print(f"❌ Could not write health status file: {e}")
        return None

if __name__ == "__main__":
    print("Testing health status file creation...")
    
    # Test unhealthy state
    print("\n1. Testing UNHEALTHY state:")
    connection_healthy = False
    last_data_received = datetime.now()  # Recent but connection unhealthy
    health_file = write_health_status()
    
    if health_file:
        with open(health_file, 'r') as f:
            data = json.load(f)
        print(f"   Connection healthy: {data['connection_healthy']}")
        print(f"   Last data received: {data['last_data_received']}")
        print(f"   Current port: {data['current_port']}")
    
    # Test healthy state
    print("\n2. Testing HEALTHY state:")
    connection_healthy = True
    last_data_received = datetime.now()  # Recent and connection healthy
    health_file = write_health_status()
    
    if health_file:
        with open(health_file, 'r') as f:
            data = json.load(f)
        print(f"   Connection healthy: {data['connection_healthy']}")
        print(f"   Last data received: {data['last_data_received']}")
        print(f"   Current port: {data['current_port']}")
    
    print(f"\n✅ Health status file test complete!")
    print(f"   File location: {health_file}")
