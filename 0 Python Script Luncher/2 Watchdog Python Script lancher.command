#!/bin/bash
# Watchdog Python Script Launcher - Auto-restart Python scripts every X minutes

cd "$(dirname "$0")"
echo "🔄 Watchdog Python Script Launcher"
echo "Opening watchdog configuration..."
echo ""

/Library/Frameworks/Python.framework/Versions/3.11/bin/python3 watchdog_python_launcher.py