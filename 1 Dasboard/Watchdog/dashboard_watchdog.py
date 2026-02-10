#!/home/penutaco/GitHub/Hydroponic\ Prototype\ V1/.venv/bin/python
"""
Dashboard Watchdog - External Process Monitor
Monitors the hydroponic dashboard and restarts it when data flow stops

Author: AI Assistant
Date: September 2025
Purpose: Ensure dashboard reliability by external process monitoring
"""

import os
import sys
import time
import json
import signal
import psutil
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import configparser

class DashboardWatchdog:
    def __init__(self, config_file="watchdog_config.ini"):
        self.config = self.load_config(config_file)
        self.setup_logging()
        self.dashboard_process = None
        self.last_restart = None
        self.restart_count = 0
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
    def load_config(self, config_file):
        """Load configuration from file or create default"""
        config = configparser.ConfigParser()
        config_path = Path(config_file)
        
        # Default configuration
        defaults = {
            'DASHBOARD': {
                'script_path': '/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard/1p2 dashboard v10 NS Manager Basic.py',
                'python_path': '/home/penutaco/GitHub/Hydroponic Prototype V1/.venv/bin/python',
                'startup_script': '/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard/Ubuntu ESP32 Serial Optimization/start_dashboard_high_priority.sh',
                'use_startup_script': 'false'
            },
            'MONITORING': {
                'data_timeout_minutes': '5',
                'check_interval_seconds': '30',
                'max_restarts_per_hour': '6',
                'initial_startup_delay': '300',
                'restart_rate_limit_minutes': '1'
            },
            'DATA_SOURCES': {
                'csv_file': '/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard/data/hydroponic_data.csv',
                'log_pattern': 'SUCCESS: ESP32 detected',
                'health_status_file': '/home/penutaco/GitHub/Hydroponic Prototype V1/0 Dasboard/data/dashboard_health.json'
            },
            'LOGGING': {
                'log_file': 'dashboard_watchdog.log',
                'log_level': 'INFO',
                'max_log_size_mb': '10'
            }
        }
        
        if not config_path.exists():
            # Create default config file
            for section, options in defaults.items():
                config.add_section(section)
                for key, value in options.items():
                    config.set(section, key, value)
            
            with open(config_path, 'w') as f:
                config.write(f)
            print(f"Created default config file: {config_path}")
        else:
            config.read(config_path)
            
        return config
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_level = getattr(logging, self.config.get('LOGGING', 'log_level', fallback='INFO'))
        log_file = self.config.get('LOGGING', 'log_file', fallback='dashboard_watchdog.log')
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def find_dashboard_process(self):
        """Find running dashboard process by name/command"""
        script_name = Path(self.config.get('DASHBOARD', 'script_path')).name
        
        for process in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(process.info['cmdline'] or [])
                if script_name in cmdline and 'python' in cmdline:
                    return process
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None
    
    def is_dashboard_healthy(self):
        """Check if dashboard is receiving data"""
        try:
            # Method 1: Check health status file (preferred)
            health_file = self.config.get('DATA_SOURCES', 'health_status_file')
            if health_file and Path(health_file).exists():
                try:
                    with open(health_file, 'r') as f:
                        health_data = json.load(f)
                    
                    # Check if health data is recent
                    last_update = datetime.fromisoformat(health_data.get('last_update', ''))
                    time_since_update = datetime.now() - last_update
                    
                    # If health file is stale (older than 2 minutes), consider unhealthy
                    if time_since_update.total_seconds() > 120:
                        self.logger.warning(f"Health status file is stale ({time_since_update.total_seconds():.1f}s old) - UNHEALTHY")
                        return False
                    
                    # Check connection health from dashboard
                    connection_healthy = health_data.get('connection_healthy', False)
                    last_data_received = health_data.get('last_data_received')
                    
                    if not connection_healthy:
                        self.logger.warning(f"Dashboard reports connection unhealthy - UNHEALTHY")
                        return False
                    
                    if last_data_received:
                        last_data_time = datetime.fromisoformat(last_data_received)
                        time_since_data = datetime.now() - last_data_time
                        timeout_minutes = self.config.getint('MONITORING', 'data_timeout_minutes', fallback=5)
                        
                        if time_since_data.total_seconds() > timeout_minutes * 60:
                            self.logger.warning(f"No sensor data for {time_since_data.total_seconds():.1f}s - UNHEALTHY")
                            return False
                    
                    self.logger.debug("Health status file indicates HEALTHY")
                    return True
                    
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    self.logger.warning(f"Error reading health status file: {e} - falling back to CSV check")
                    # Fall through to CSV check
            
            # Method 2: Check CSV file modification time (fallback)
            csv_file = self.config.get('DATA_SOURCES', 'csv_file')
            if csv_file and Path(csv_file).exists():
                file_mod_time = datetime.fromtimestamp(Path(csv_file).stat().st_mtime)
                time_since_mod = datetime.now() - file_mod_time
                timeout_minutes = self.config.getint('MONITORING', 'data_timeout_minutes', fallback=5)
                
                if time_since_mod.total_seconds() < timeout_minutes * 60:
                    self.logger.debug(f"CSV file updated {time_since_mod.total_seconds():.1f}s ago - HEALTHY")
                    return True
                else:
                    self.logger.warning(f"CSV file not updated for {time_since_mod.total_seconds():.1f}s - UNHEALTHY")
                    return False
            
            # Method 3: Check process responsiveness (basic check)
            process = self.find_dashboard_process()
            if not process:
                self.logger.error("Dashboard process not found - UNHEALTHY")
                return False
            
            # Check if process is responsive (not zombie/defunct)
            if process.status() in ['zombie', 'defunct']:
                self.logger.error(f"Dashboard process is {process.status()} - UNHEALTHY")
                return False
            
            # If no other methods available, assume healthy if process exists
            self.logger.warning("Using fallback health check - process exists")
            return True
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False
    
    def kill_dashboard_process(self):
        """Forcefully kill dashboard process and cleanup"""
        try:
            # Kill by process name pattern
            script_name = Path(self.config.get('DASHBOARD', 'script_path')).name
            result = subprocess.run([
                'pkill', '-f', script_name
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                self.logger.info("Dashboard process killed successfully")
            else:
                self.logger.warning("pkill returned non-zero exit code, process may not exist")
            
            # Wait a moment for cleanup
            time.sleep(2)
            
            # Verify process is dead
            if self.find_dashboard_process():
                self.logger.warning("Process still running, trying SIGKILL...")
                subprocess.run(['pkill', '-9', '-f', script_name], timeout=5)
                time.sleep(1)
            
        except Exception as e:
            self.logger.error(f"Error killing dashboard process: {e}")
    
    def start_dashboard_process(self):
        """Start dashboard process exactly like manual launch"""
        try:
            # Get the exact command used for manual launch
            python_path = self.config.get('DASHBOARD', 'python_path')
            script_path = self.config.get('DASHBOARD', 'script_path')
            
            # Build the exact command as you would type it manually
            manual_command = f'"{python_path}" "{script_path}"'
            
            self.logger.info(f"Starting dashboard with manual command: {manual_command}")
            
            # Use shell=True to execute exactly as if typed in terminal
            # Start in background (&) so watchdog doesn't block
            # REMOVED > /dev/null 2>&1 to show dashboard output and errors
            shell_command = f'cd "{os.path.dirname(script_path)}" && {manual_command} &'
            
            # Execute the command via shell (same as manual typing)
            result = subprocess.run(shell_command, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.info("Dashboard command executed successfully")
            else:
                self.logger.error(f"Dashboard command failed: {result.stderr}")
                return False
            
            # Wait for initial startup
            initial_delay = self.config.getint('MONITORING', 'initial_startup_delay', fallback=60)
            self.logger.info(f"Waiting {initial_delay}s for dashboard startup...")
            time.sleep(initial_delay)
            
            # Verify process started
            if self.find_dashboard_process():
                self.logger.info("Dashboard started successfully")
                return True
            else:
                self.logger.error("Dashboard process not found after startup")
                return False
                
        except Exception as e:
            self.logger.error(f"Error starting dashboard process: {e}")
            return False
    
    def restart_dashboard(self):
        """Restart dashboard with rate limiting"""
        now = datetime.now()
        max_restarts = self.config.getint('MONITORING', 'max_restarts_per_hour', fallback=6)
        
        # Check restart rate limiting
        if self.last_restart:
            rate_limit_minutes = self.config.getint('MONITORING', 'restart_rate_limit_minutes', fallback=1)
            time_since_restart = now - self.last_restart
            if time_since_restart < timedelta(minutes=rate_limit_minutes):
                self.logger.warning(f"Rate limiting: Last restart was {time_since_restart.total_seconds():.1f}s ago (limit: {rate_limit_minutes}min)")
                return False
        
        # Reset restart count every hour
        if not self.last_restart or (now - self.last_restart) > timedelta(hours=1):
            self.restart_count = 0
        
        if self.restart_count >= max_restarts:
            self.logger.error(f"Max restarts per hour ({max_restarts}) reached. Manual intervention required.")
            return False
        
        self.logger.info(f"🔄 RESTARTING DASHBOARD (attempt {self.restart_count + 1}/{max_restarts})")
        
        # Kill existing process
        self.kill_dashboard_process()
        
        # Start new process
        if self.start_dashboard_process():
            self.last_restart = now
            self.restart_count += 1
            self.logger.info("✅ Dashboard restart completed successfully")
            return True
        else:
            self.logger.error("❌ Dashboard restart failed")
            return False
    
    def run(self):
        """Main watchdog loop"""
        self.logger.info("🐕 Dashboard Watchdog starting...")
        self.logger.info(f"Monitor interval: {self.config.getint('MONITORING', 'check_interval_seconds')}s")
        self.logger.info(f"Data timeout: {self.config.getint('MONITORING', 'data_timeout_minutes')}min")
        
        # Initial dashboard start if not running
        if not self.find_dashboard_process():
            self.logger.info("Dashboard not running, starting initial instance...")
            self.start_dashboard_process()
        else:
            self.logger.info("Dashboard process found, monitoring existing instance")
        
        check_interval = self.config.getint('MONITORING', 'check_interval_seconds', fallback=30)
        
        while self.running:
            try:
                # Check dashboard health
                if not self.is_dashboard_healthy():
                    self.logger.warning("🚨 Dashboard unhealthy, attempting restart...")
                    if not self.restart_dashboard():
                        self.logger.error("Failed to restart dashboard, waiting before retry...")
                        time.sleep(60)  # Wait longer on failure
                else:
                    self.logger.debug("Dashboard healthy ✅")
                
                # Wait for next check
                time.sleep(check_interval)
                
            except KeyboardInterrupt:
                self.logger.info("Keyboard interrupt received, shutting down...")
                break
            except Exception as e:
                self.logger.error(f"Watchdog error: {e}")
                time.sleep(30)  # Wait before retry on error
        
        self.logger.info("🐕 Dashboard Watchdog stopped")

def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    else:
        config_file = "watchdog_config.ini"
    
    watchdog = DashboardWatchdog(config_file)
    watchdog.run()

if __name__ == "__main__":
    main()
