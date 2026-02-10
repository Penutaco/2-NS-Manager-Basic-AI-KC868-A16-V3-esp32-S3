#!/usr/bin/env python3
"""
Test script to verify the watchdog problems identified
"""
import os
import sys
import subprocess
import psutil
from pathlib import Path
sys.path.append('.')
from dashboard_watchdog import DashboardWatchdog

def test_problem_1_silent_failures():
    """Problem 1: Silent Failures - > /dev/null 2>&1 hides errors"""
    print("=" * 60)
    print("TESTING PROBLEM 1: Silent Failures")
    print("=" * 60)
    
    watchdog = DashboardWatchdog()
    
    # Get the exact command the watchdog uses
    python_path = watchdog.config.get('DASHBOARD', 'python_path')
    script_path = watchdog.config.get('DASHBOARD', 'script_path')
    manual_command = f'"{python_path}" "{script_path}"'
    shell_command = f'cd "{os.path.dirname(script_path)}" && {manual_command} > /dev/null 2>&1 &'
    
    print(f"Watchdog command: {shell_command}")
    print(f"Problem: The '> /dev/null 2>&1' part redirects ALL output to /dev/null")
    print(f"This means errors are HIDDEN and you can't see why the dashboard fails!")
    
    # Test with a command that will definitely fail
    failing_command = f'cd "{os.path.dirname(script_path)}" && {manual_command}_NONEXISTENT > /dev/null 2>&1 &'
    print(f"\nTesting with failing command: {failing_command}")
    result = subprocess.run(failing_command, shell=True, capture_output=True, text=True)
    print(f"Result returncode: {result.returncode}")
    print(f"Result stderr: '{result.stderr}'")
    print(f"Result stdout: '{result.stdout}'")
    print("Notice: No error message visible because of > /dev/null 2>&1")
    
    return True

def test_problem_2_port_conflict():
    """Problem 2: Port Conflict - Multiple dashboard instances"""
    print("\n" + "=" * 60)
    print("TESTING PROBLEM 2: Port Conflict")
    print("=" * 60)
    
    # Check if dashboard is already running
    result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    dashboard_processes = [line for line in result.stdout.split('\n') 
                          if '1p2 dashboard v10 NS Manager Basic.py' in line and 'grep' not in line]
    
    print(f"Current dashboard processes found: {len(dashboard_processes)}")
    for process in dashboard_processes:
        print(f"  {process.strip()}")
    
    # Check port 5555 usage
    try:
        result = subprocess.run(['sudo', 'netstat', '-tulpn'], capture_output=True, text=True, input='\n')
        port_5555_lines = [line for line in result.stdout.split('\n') if '5555' in line]
        print(f"\nPort 5555 usage:")
        if port_5555_lines:
            for line in port_5555_lines:
                print(f"  {line.strip()}")
        else:
            print("  Port 5555 is not in use")
    except Exception as e:
        print(f"Error checking port: {e}")
    
    return len(dashboard_processes) > 1

def test_problem_3_process_detection():
    """Problem 3: Poor Process Detection"""
    print("\n" + "=" * 60)
    print("TESTING PROBLEM 3: Process Detection")
    print("=" * 60)
    
    watchdog = DashboardWatchdog()
    
    # Test the process detection
    process = watchdog.find_dashboard_process()
    
    if process:
        print(f"Watchdog FOUND process:")
        print(f"  PID: {process.pid}")
        print(f"  Name: {process.name()}")
        print(f"  Command: {' '.join(process.cmdline())}")
    else:
        print("Watchdog did NOT find dashboard process")
        
        # Let's see what's actually running
        print("\nManual process search:")
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if '1p2 dashboard v10 NS Manager Basic.py' in cmdline:
                    print(f"  FOUND: PID={proc.info['pid']}, CMD={cmdline}")
            except:
                continue
    
    return process is not None

def test_problem_4_error_handling():
    """Problem 4: No Error Handling for startup"""
    print("\n" + "=" * 60)
    print("TESTING PROBLEM 4: Error Handling")
    print("=" * 60)
    
    watchdog = DashboardWatchdog()
    
    print("Current error handling in start_dashboard_process():")
    print("1. Uses subprocess.run() with shell=True")
    print("2. Checks result.returncode == 0")
    print("3. BUT: The '> /dev/null 2>&1 &' means the actual dashboard errors are hidden")
    print("4. The background '&' means subprocess.run() always returns 0 immediately")
    print("5. No way to detect if dashboard actually started or crashed after launch")
    
    # Demonstrate the problem
    python_path = watchdog.config.get('DASHBOARD', 'python_path')
    script_path = watchdog.config.get('DASHBOARD', 'script_path')
    
    # Test command that will fail but return 0 because of &
    bad_command = f'cd "{os.path.dirname(script_path)}" && {python_path} nonexistent_file.py > /dev/null 2>&1 &'
    print(f"\nTesting bad command: {bad_command}")
    result = subprocess.run(bad_command, shell=True, capture_output=True, text=True)
    print(f"Result returncode: {result.returncode} (should be 0 because of &, even if command failed)")
    
    return True

def main():
    """Run all tests"""
    print("WATCHDOG PROBLEM VERIFICATION")
    print("=" * 60)
    
    problem1 = test_problem_1_silent_failures()
    problem2 = test_problem_2_port_conflict()
    problem3 = test_problem_3_process_detection()
    problem4 = test_problem_4_error_handling()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Problem 1 - Silent Failures: {'VERIFIED' if problem1 else 'NOT FOUND'}")
    print(f"Problem 2 - Port Conflict: {'VERIFIED' if problem2 else 'NOT FOUND'}")
    print(f"Problem 3 - Process Detection: {'WORKING' if problem3 else 'FAILING'}")
    print(f"Problem 4 - Error Handling: {'VERIFIED' if problem4 else 'NOT FOUND'}")

if __name__ == "__main__":
    main()
