#!/home/penutaco/GitHub/Hydroponic\ Prototype\ V1/.venv/bin/python
"""
Simple Dashboard Watchdog
Monitors dashboard health and restarts when needed

Workflow:
1. Start dashboard like manual startup
2. Check JSON file every 1 minute
3. If health_monitor_active: false for 5+ minutes
4. Kill dashboard process
5. Kill ZMQ processes
6. Restart dashboard

Author: AI Assistant
Date: September 2025
"""

import os
import sys
import time
import json
import signal
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

class SimpleDashboardWatchdog:
    def __init__(self):
        # Configuration
        self.python_path = "/home/penutaco/GitHub/Hydroponic Prototype V1/.venv/bin/python"
        self.script_path = "/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard/1p2 dashboard v10 NS Manager Basic.py"
        self.health_file = "/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard/data/dashboard_health.json"
        self.check_interval = 60  # Check every 1 minute
        self.unhealthy_timeout = 300  # 5 minutes in seconds
        
        self.running = True
        self.unhealthy_since = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        print("🐕 Simple Dashboard Watchdog")
        print(f"Check interval: {self.check_interval} seconds")
        print(f"Unhealthy timeout: {self.unhealthy_timeout} seconds")
        print("-" * 50)
        
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        print(f"\nReceived signal {signum}, shutting down...")
        self.running = False
        
    def start_dashboard(self):
        """Start dashboard exactly like manual startup"""
        print("🚀 Starting dashboard...")
        
        # Build exact manual command
        dashboard_dir = os.path.dirname(self.script_path)
        command = f'cd "{dashboard_dir}" && "{self.python_path}" "{os.path.basename(self.script_path)}"'
        
        print(f"Command: {command}")
        
        # Start in background (no output redirection - let it show)
        subprocess.Popen(command, shell=True)
        
        print("✅ Dashboard started")
        time.sleep(3)  # Give it a moment to start
        
    def kill_dashboard(self):
        """Kill dashboard and ZMQ processes"""
        print("💀 Killing dashboard...")
        
        # Kill dashboard process
        script_name = os.path.basename(self.script_path)
        subprocess.run(['pkill', '-f', script_name], capture_output=True)
        
        # Kill any remaining ZMQ processes on port 5555
        try:
            result = subprocess.run(['lsof', '-t', '-i:5555'], capture_output=True, text=True)
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    subprocess.run(['kill', pid], capture_output=True)
                print(f"Killed ZMQ processes: {pids}")
        except:
            pass
            
        time.sleep(2)  # Wait for cleanup
        print("✅ Processes killed")
        
    def check_health(self):
        """Check if dashboard is healthy based on JSON file"""
        try:
            if not Path(self.health_file).exists():
                print("⚠️  Health file missing")
                return False
                
            with open(self.health_file, 'r') as f:
                health_data = json.load(f)
                
            # Check if health_monitor_active is false
            health_active = health_data.get('health_monitor_active', False)
            
            if not health_active:
                print("❌ health_monitor_active: false")
                return False
            else:
                print("✅ health_monitor_active: true")
                return True
                
        except Exception as e:
            print(f"❌ Error reading health file: {e}")
            return False
            
    def run(self):
        """Main watchdog loop"""
        # Start initial dashboard
        self.start_dashboard()
        
        while self.running:
            try:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking health...")
                
                is_healthy = self.check_health()
                
                if is_healthy:
                    # Reset unhealthy timer
                    if self.unhealthy_since:
                        print("🎉 Dashboard recovered!")
                    self.unhealthy_since = None
                else:
                    # Start or continue unhealthy timer
                    if not self.unhealthy_since:
                        self.unhealthy_since = datetime.now()
                        print(f"⏰ Started unhealthy timer at {self.unhealthy_since.strftime('%H:%M:%S')}")
                    else:
                        unhealthy_duration = datetime.now() - self.unhealthy_since
                        print(f"⏰ Unhealthy for {int(unhealthy_duration.total_seconds())}s (limit: {self.unhealthy_timeout}s)")
                        
                        if unhealthy_duration.total_seconds() >= self.unhealthy_timeout:
                            print("🚨 Dashboard unhealthy for too long! Restarting...")
                            self.kill_dashboard()
                            self.start_dashboard()
                            self.unhealthy_since = None
                
                # Wait for next check
                print(f"😴 Waiting {self.check_interval} seconds...")
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                print("\nKeyboard interrupt received")
                break
            except Exception as e:
                print(f"❌ Watchdog error: {e}")
                time.sleep(10)
                
        print("🐕 Simple Dashboard Watchdog stopped")

def main():
    """Main entry point"""
    watchdog = SimpleDashboardWatchdog()
    watchdog.run()

if __name__ == "__main__":
    main()
