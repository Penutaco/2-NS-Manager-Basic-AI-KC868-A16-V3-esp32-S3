#!/usr/bin/env python3
"""
Watchdog Python Script Launcher - Auto-restart Python scripts at regular intervals
Prevents script hangs and memory leaks by forcefully restarting scripts every X minutes.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import subprocess
import os
import sys
import time
import signal
import threading
from datetime import datetime

class WatchdogLauncher:
    def __init__(self):
        self.temp_script_path = None
        self.script_path = None
        self.restart_interval = 0
        self.running = False
        self.restart_count = 0
        
    def get_restart_time(self):
        """Get restart interval from user"""
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        
        while True:
            try:
                restart_time = simpledialog.askfloat(
                    "Watchdog Timer",
                    "Enter restart interval (minutes):\n\n"
                    "• Recommended: 5-30 minutes\n"
                    "• Minimum: 0.1 minutes (6 seconds)\n"
                    "• Maximum: 1440 minutes (24 hours)",
                    minvalue=0.1,
                    maxvalue=1440.0,
                    initialvalue=5.0
                )
                
                if restart_time is None:
                    print("❌ No restart time specified. Exiting.")
                    return None
                    
                self.restart_interval = restart_time * 60  # Convert to seconds
                print(f"⏱️  Restart interval set to: {restart_time} minutes ({self.restart_interval} seconds)")
                return restart_time
                
            except Exception as e:
                messagebox.showerror("Error", f"Invalid input: {e}")
                continue
    
    def select_python_script(self):
        """Select Python script to run with watchdog"""
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        
        # Configure file dialog
        filetypes = [
            ("Python files", "*.py"),
            ("All files", "*.*")
        ]
        
        # Open file dialog
        script_path = filedialog.askopenfilename(
            title="Select Python Script for Watchdog Monitoring",
            filetypes=filetypes,
            initialdir=os.path.expanduser("~/Desktop")
        )
        
        if not script_path:
            print("❌ No script selected. Exiting.")
            return None
            
        if not script_path.endswith('.py'):
            messagebox.showwarning("Warning", "Selected file is not a Python script (.py)")
            return None
            
        if not os.path.exists(script_path):
            messagebox.showerror("Error", f"File not found: {script_path}")
            return None
        
        self.script_path = script_path
        print(f"📝 Selected script: {os.path.basename(script_path)}")
        print(f"📁 Directory: {os.path.dirname(script_path)}")
        return script_path
    
    def start_script(self):
        """Start the Python script in a NEW terminal window"""
        python_path = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
        script_dir = os.path.dirname(self.script_path)
        script_name = os.path.basename(self.script_path)
        
        try:
            # Kill any existing processes that might be using ports (like ZMQ)
            self.cleanup_existing_processes()
            
            # Create a temporary shell script to run in new terminal
            import tempfile
            
            # Create temporary script file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as temp_script:
                temp_script.write('#!/bin/bash\n')
                temp_script.write(f'cd "{script_dir}"\n')
                temp_script.write(f'echo "🚀 Starting Python script: {script_name}"\n')
                temp_script.write(f'echo "📁 Directory: {script_dir}"\n')
                temp_script.write(f'echo "⏱️  Started at: $(date)"\n')
                temp_script.write(f'echo "==============================================="\n')
                temp_script.write(f'"{python_path}" "{self.script_path}"\n')
                temp_script.write(f'echo "==============================================="\n')
                temp_script.write(f'echo "✅ Script finished at: $(date)"\n')
                temp_script.write(f'echo "🔄 This terminal will close in 3 seconds..."\n')
                temp_script.write(f'sleep 3\n')
                temp_script.write(f'exit\n')  # This will close the terminal
                temp_script_path = temp_script.name
            
            # Make the temporary script executable
            os.chmod(temp_script_path, 0o755)
            
            # Use the 'open' command to run the script in a new Terminal window
            result = subprocess.run([
                'open', '-a', 'Terminal', temp_script_path
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                # Store the temp script path for cleanup later
                self.temp_script_path = temp_script_path
                
                self.restart_count += 1
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"🚀 [{timestamp}] Started script in NEW terminal (Run #{self.restart_count}): {script_name}")
                print(f"   Script Directory: {script_dir}")
                print(f"   Terminal will auto-close after script finishes")
                
                return True
            else:
                print(f"❌ Error opening new terminal: {result.stderr}")
                # Clean up temp file if failed
                try:
                    os.unlink(temp_script_path)
                except:
                    pass
                return False
                
        except Exception as e:
            print(f"❌ Error starting script in new terminal: {e}")
            return False
    
    def cleanup_existing_processes(self):
        """Kill any existing Python processes that might be using ports"""
        try:
            # Find and kill Python processes running the same script
            script_name = os.path.basename(self.script_path)
            
            # Use pkill to find and kill processes
            subprocess.run([
                'pkill', '-f', script_name
            ], capture_output=True, timeout=5)
            
            # Also try to free up common ports (ZMQ, serial, etc.)
            subprocess.run([
                'pkill', '-f', 'python.*5555'
            ], capture_output=True, timeout=5)
            
            print(f"   🧹 Cleaned up existing processes for: {script_name}")
            
        except Exception as e:
            print(f"   ⚠️ Cleanup warning: {e}")
            # Don't fail if cleanup has issues
    
    def kill_script(self):
        """Close the terminal window and clean up temp files"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"🔪 [{timestamp}] Waiting for terminal window to close...")
        
        # The terminal window will close when the script finishes
        # We just need to clean up the temporary script file
        if hasattr(self, 'temp_script_path') and self.temp_script_path:
            try:
                # Wait a moment for the terminal to finish
                time.sleep(1)
                
                # Clean up the temporary script file
                if os.path.exists(self.temp_script_path):
                    os.unlink(self.temp_script_path)
                    print(f"   🗑️ Cleaned up temp script: {self.temp_script_path}")
                
                print("   ✅ Terminal window cleanup completed")
                    
            except Exception as e:
                print(f"❌ Error during cleanup: {e}")
                
        # Clean up
        self.temp_script_path = None
    
    def watchdog_loop(self):
        """Main watchdog loop"""
        print("=" * 80)
        print("🐕 WATCHDOG STARTED")
        print(f"📝 Script: {os.path.basename(self.script_path)}")
        print(f"⏱️  Restart interval: {self.restart_interval/60:.1f} minutes")
        print(f"🔄 Mode: Auto-restart every {self.restart_interval} seconds")
        print("=" * 80)
        print("💡 Press Ctrl+C to stop the watchdog")
        print("")
        
        self.running = True
        
        try:
            while self.running:
                # Start the script
                if self.start_script():
                    # Wait for restart interval
                    print(f"⏳ Next restart in {self.restart_interval/60:.1f} minutes...")
                    time.sleep(self.restart_interval)
                    
                    # Close terminal and restart
                    self.kill_script()
                    print(f"🔄 Preparing for restart...")
                    time.sleep(2)  # Brief pause between close and restart
                else:
                    print("❌ Failed to start script. Retrying in 10 seconds...")
                    time.sleep(10)
                    
        except KeyboardInterrupt:
            print("\n🛑 Watchdog interrupted by user")
            self.stop()
        except Exception as e:
            print(f"❌ Watchdog error: {e}")
            self.stop()
    
    def stop(self):
        """Stop the watchdog"""
        print("🛑 Stopping watchdog...")
        self.running = False
        self.kill_script()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"📊 [{timestamp}] Watchdog Summary:")
        print(f"   • Total restarts: {self.restart_count}")
        print(f"   • Script: {os.path.basename(self.script_path) if self.script_path else 'N/A'}")
        print("✅ Watchdog stopped")
    
    def run(self):
        """Main entry point"""
        print("🔄 Watchdog Python Script Launcher")
        print("=" * 50)
        
        # Step 1: Get restart time
        restart_time = self.get_restart_time()
        if restart_time is None:
            return
        
        # Step 2: Select script
        script_path = self.select_python_script()
        if script_path is None:
            return
        
        # Confirmation
        script_name = os.path.basename(script_path)
        confirm = messagebox.askyesno(
            "Confirm Watchdog Setup",
            f"Ready to start watchdog:\n\n"
            f"📝 Script: {script_name}\n"
            f"⏱️  Restart every: {restart_time} minutes\n"
            f"🔄 Mode: Auto-restart (infinite loop)\n\n"
            f"⚠️  Warning: Script will be forcefully killed and restarted!\n\n"
            f"Start watchdog?"
        )
        
        if not confirm:
            print("❌ Watchdog cancelled by user")
            return
        
        # Start watchdog
        try:
            self.watchdog_loop()
        finally:
            # Keep terminal open
            input("\nPress Enter to close...")

def main():
    """Main function"""
    try:
        launcher = WatchdogLauncher()
        launcher.run()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        input("Press Enter to close...")

if __name__ == "__main__":
    main()