================================================================================
                           BRANCH: EC-Regression-Fixed
================================================================================

Branch Created: August 11, 2025
Parent Branch: master
Purpose: Fix electrical conductivity (EC) sensor regression issues and update calibration

================================================================================
CHANGES IMPLEMENTED
================================================================================

✅ COMPLETED MODIFICATIONS:

1. EC CALIBRATION CURVE UPDATE:
   - REMOVED: Complex 3rd-order polynomial calibration
     OLD: float mScmValue = (133.42 * V³ - 255.86 * V² + 857.39 * V) * 0.001
   - ADDED: Linear calibration for D1/2 dilution
     NEW: float mScmValue = 0.885 * compensationVoltage + 0.2925
   
   Location: ECSensor.h, processECSensor() function
   Benefits: 
   - Much more accurate for D1/2 dilution solutions
   - Simpler and more stable computation
   - Eliminates polynomial regression issues

2. SERIAL LOGGING CONSISTENCY FIX:
   - FIXED: Inconsistent PRGSample cycle messages
     OLD: First cycle: "Switching to PRGSample sequence..."
          Subsequent: "Starting new PRGSample cycle (X of 286)"
   - NOW: Consistent format for all cycles:
          "Starting new PRGSample cycle (1 of 286)"
          "Starting new PRGSample cycle (2 of 286)" etc.
   
   Location: main.cpp, event sequencing logic (~line 354)
   Benefits:
   - Consistent serial output formatting
   - Better cycle tracking and monitoring
   - Improved system debugging capabilities

================================================================================
CALIBRATION CURVE DETAILS
================================================================================

New Linear Equation: EC = 0.885 × Voltage + 0.2925 (mS/cm)

Calibration Parameters:
- Slope: 0.885 mS/cm per Volt
- Y-intercept: 0.2925 mS/cm
- Solution: D1/2 dilution specific calibration
- Range: 0-4V input voltage range

Example Readings:
- 0V → 0.29 mS/cm
- 1V → 1.18 mS/cm  
- 2V → 2.06 mS/cm
- 3V → 2.95 mS/cm

================================================================================
TESTING STATUS
================================================================================

[ ] Test with distilled water (should read ~0.29 mS/cm)
[ ] Test with D1/2 calibration solutions
[ ] Verify readings are stable over time
[ ] Compare with reference EC meter
[ ] Test temperature compensation functionality
[ ] Validate integration with nutrient dosing system

================================================================================
PENDING ISSUES TO ADDRESS
================================================================================

🔧 STILL NEEDS FIXING:

1. TEMPERATURE COMPENSATION:
   - Current: Fixed at 25°C (always compensation = 1.0)
   - Needed: Dynamic temperature from DS18B20 sensor
   - Location: ECSensor.h, line with TEMP 25.0

2. CALIBRATION SYSTEM:
   - Current: No dynamic calibration variables
   - Needed: ec_cal_points[], ec_cal_expected[] arrays
   - Similar to existing pH calibration system

3. CALIBRATION EVENTS:
   - Current: All EC values in PRGCal.h are 0.0
   - Needed: Proper EC calibration event values

================================================================================
FILES MODIFIED
================================================================================

✅ Modified:
- ECSensor.h (calibration curve updated)
- main.cpp (serial logging consistency fixed)

🔧 Still needs modification:
- globals.h (add EC calibration variables)
- globals.cpp (implement EC calibration arrays)
- PRGCal.h (add EC calibration event values)
- Event.h (verify EC calibration support)

================================================================================
MERGE CRITERIA
================================================================================

This branch will be ready to merge when:
✅ Linear calibration curve implemented (DONE)
✅ Serial logging consistency fixed (DONE)
[ ] Temperature compensation fixed
[ ] Dynamic calibration system implemented  
[ ] All EC sensor tests pass
[ ] Integration testing completed
[ ] Documentation updated

================================================================================
DASHBOARD HEALTH MONITORING UPDATES (August 30, 2025)
================================================================================

✅ HEALTH MONITORING SYSTEM IMPLEMENTED:
• Added comprehensive USB connection monitoring with 30s check intervals
• Implemented automatic ESP32 reconnection with 3 retry attempts  
• Added dynamic USB port scanning (/dev/ttyUSB*) when connections fail
• Real-time connection status display in dashboard UI with emoji indicators
• Background health monitor thread with industrial reliability standards
• Connection log with timestamped status messages (✅/❌/⚠️/🔍)
• Updated serial port from /dev/ttyUSB0 to /dev/ttyUSB1
• Fixed PlatformIO path to use full installation path
• Added dash-bootstrap-components to requirements.txt
• Created test script for health monitoring validation

================================================================================
DASHBOARD ARCHITECTURE EVOLUTION
================================================================================

So the dashboard is actually:
1.	✅ Data Logger: Saves serial data to CSV
2.	✅ Real-Time Visualizer: Displays live sensor graphs
3.	✅ Communication Hub: Bridges dosing controller ↔ ESP32
4.	✅ Event Processor: Tracks and synchronizes hydroponic events
5.	✅ File Manager: Handles log rotation and multiple data formats
6.	✅ Flexible Reader: Can operate from serial OR CSV files
7.	✅ Health Monitor: Automatic USB connection recovery system

Dashboard Broken down into 2 separate programs:

🔧 DATA COLLECTION (data_collection.py):
- ✅ Data Logger: Saves serial data to CSV files
- ✅ Communication Hub: ZMQ server for dosing controller communication
- ✅ Event Processor: Tracks PRGCal/PRGSample events and measurements
- ✅ File Manager: Creates timestamped CSV files (sensor_data_*.csv, event_data_*.csv)
- ✅ Serial Interface: Direct ESP32 communication via PlatformIO monitor
- ✅ Real-time Processing: Handles pH/EC measurement synchronization
- Port: ZMQ server on tcp://*:5555

📊 VISUALIZATION (visualization.py):
- ✅ Real-Time Visualizer: Web-based sensor graph display
- ✅ CSV Reader: Monitors CSV files for new data (no serial dependency)
- ✅ Y-axis Controls: Advanced graph controls (center point + signal range)
- ✅ Time Window Support: Configurable visualization windows (5s to 8 hours)
- ✅ Data Processing: Handles inf/nan values and calibration data properly
- ✅ Event Log Display: Shows recent system events
- Port: Web interface on http://localhost:8051

🎯 SEPARATION BENEFITS:
- Independent operation: Visualization works without ESP32 connection
- Better reliability: Data collection continues even if visualization crashes
- Easier development: Can test visualization with historical data
- Resource efficiency: Run only needed components
- Deployment flexibility: Can run on separate machines

================================================================================
NOTES
================================================================================

- EC sensor: Using ADS1115 channel A0
- Solution: D1/2 dilution for hydroponic nutrients
- Calibration: Linear fit specifically for this dilution ratio
- Temperature sensor: DS18B20 available but not yet integrated for EC compensation
- Architecture: Monolithic dashboard split into data collection + visualization components

Last Updated: August 30, 2025
Developer: [Your name here]
================================================================================