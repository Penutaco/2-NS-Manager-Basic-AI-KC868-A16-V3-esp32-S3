#!/usr/bin/env python3
"""
Python Script Launcher - GUI file selector for running Python scripts with Python 3.11
Double-click the .command version to use this tool.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import os
import sys

def select_and_run_python_script():
    """Open file dialog to select and run a Python script"""
    
    # Create root window (hidden)
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    
    # Configure file dialog
    filetypes = [
        ("Python files", "*.py"),
        ("All files", "*.*")
    ]
    
    # Open file dialog
    script_path = filedialog.askopenfilename(
        title="Select Python Script to Run",
        filetypes=filetypes,
        initialdir=os.path.expanduser("~/Desktop")
    )
    
    # Check if user selected a file
    if not script_path:
        print("No file selected. Exiting.")
        return
    
    if not script_path.endswith('.py'):
        messagebox.showwarning("Warning", "Selected file is not a Python script (.py)")
        return
    
    if not os.path.exists(script_path):
        messagebox.showerror("Error", f"File not found: {script_path}")
        return
    
    # Python 3.11 path
    python_path = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
    
    # Get directory of the script
    script_dir = os.path.dirname(script_path)
    script_name = os.path.basename(script_path)
    
    print(f"🚀 Launching Python script: {script_name}")
    print(f"📁 Directory: {script_dir}")
    print(f"🐍 Using Python: {python_path}")
    print("=" * 60)
    
    try:
        # Change to script directory and run
        os.chdir(script_dir)
        
        # Run the Python script
        result = subprocess.run([python_path, script_path], 
                              capture_output=False, 
                              text=True)
        
        print("=" * 60)
        print(f"✅ Script finished with exit code: {result.returncode}")
        
    except FileNotFoundError:
        print(f"❌ Error: Python 3.11 not found at {python_path}")
        print("Please check your Python 3.11 installation.")
        
    except Exception as e:
        print(f"❌ Error running script: {e}")
    
    # Keep terminal open
    input("\nPress Enter to close...")

if __name__ == "__main__":
    select_and_run_python_script()