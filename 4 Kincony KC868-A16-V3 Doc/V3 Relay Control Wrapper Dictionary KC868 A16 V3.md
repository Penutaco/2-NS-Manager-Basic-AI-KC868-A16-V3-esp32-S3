# Relay Control Wrapper Dictionary
## KC868-A16 Relay Configuration Reference

---

## 📋 Hardware Overview

### I2C Configuration (ESP32-S3)
- **I2C SDA Pin**: GPIO 9
- **I2C SCL Pin**: GPIO 10
- **PCF8574 #1 Address**: 0x24 (Controls Y1-Y8)
- **PCF8574 #2 Address**: 0x25 (Controls Y9-Y16)

### Important Note
**GPIO Pin Numbers in Relay Mapping**: The GPIO numbers shown in the relay mapping table (2, 9, 10, etc.) are **logical identifiers** used in the relay_wrapper code, NOT physical ESP32-S3 GPIO pins. All relay control happens via I2C (GPIO 9=SDA, GPIO 10=SCL). These logical GPIO numbers are translated to PCF8574 I2C commands by the relay wrapper.

---

## 🔌 Relay Mapping

### Active Relays (In Use)

**Note**: GPIO Pin numbers below are **logical identifiers** for code compatibility, not physical ESP32-S3 pins.

| Relay | GPIO Pin (Logical) | I2C Addr | Bit | Physical Terminal | Function | Description |
|-------|----------|----------|-----|-------------------|----------|-------------|
| **Y1** | GPIO 2 | 0x24 | 0 | Y1 | V1 Valve | H2O/Air Vent |
| **Y2** | GPIO 9 | 0x24 | 1 | Y2 | V2 Valve | Sample/Comun |
| **Y3** | GPIO 10 | 0x24 | 2 | Y3 | V5 Valve | In pH=4/Comun |
| **Y4** | GPIO 12 | 0x24 | 3 | Y4 | V6 Valve | In pH=7/Comun |
| **Y5** | GPIO 13 | 0x24 | 4 | Y5 | PP2 Pump | Input to Sensor |
| **Y6** | GPIO 14 | 0x24 | 5 | Y6 | PP1 Pump | Output from System |
| **Y7** | GPIO 15 | 0x24 | 6 | Y7 | V4 Valve | OFF=TANK, ON=V3 |
| **Y8** | GPIO 18 | 0x24 | 7 | Y8 | V3 Valve | pH Switch (OFF=4.01, ON=6.86) |
| **Y9** | GPIO 19 | 0x25 | 0 | Y9 | Water Pump | Dilution (EC decrease) |
| **Y10** | GPIO 23 | 0x25 | 1 | Y10 | EC+ Solution B | Nutrient B Dosing |
| **Y11** | GPIO 25 | 0x25 | 2 | Y11 | EC+ Solution A | Nutrient A Dosing |
| **Y12** | GPIO 26 | 0x25 | 3 | Y12 | pH- Pump | Decreases pH |
| **Y13** | GPIO 27 | 0x25 | 4 | Y13 | pH+ Pump | Increases pH |
| **Y14** | GPIO 33 | 0x25 | 5 | Y14 | EC+ Solution C | Nutrient C Dosing |

### Available Relays (Unused)

| Relay | I2C Addr | Bit | Physical Terminal | Status |
|-------|----------|-----|-------------------|--------|
| **Y15** | 0x25 | 6 | Y15 | Available |
| **Y16** | 0x25 | 7 | Y16 | Available |

---

## 💻 Code Usage

### Control Functions

```cpp
// Include the wrapper
#include "relay_wrapper.h"

// Turn relay ON
relayWrite(27, HIGH);  // Activates Y1 (pH+ pump)

// Turn relay OFF
relayWrite(27, LOW);   // Deactivates Y1

// Configure pin mode (handled automatically by wrapper)
relayPinMode(27, OUTPUT);

// Initialize all relays to OFF
initializeRelays();
```

### Serial Commands

```
TEST_PIN_27      - Test Y1 relay for 10 seconds
TEST_PIN_26      - Test Y2 relay for 10 seconds
TEST_PIN_25      - Test Y3 relay for 10 seconds
RESET            - Turn all active relays OFF
INIT             - Turn all active relays OFF
```

### JSON Dosing Commands

```json
{
  "action": "dose",
  "pin": 27,
  "duration_ms": 5000,
  "pump_type": "pH+"
}
```

**Valid pins**: 27, 26, 25, 23, 33, 19, 14

---

## 🔧 Hardware Terminals

### Board Sections

1. **Y1-Y16**: Relay output terminals (connect pumps here)
2. **CH1-CH4**: Analog input channels (A1=GPIO4, A2=GPIO6, A3=GPIO7, A4=GPIO5)
3. **1-Wire**: Temperature sensors (GPIO 47, 48, 38)
4. **X1-X16**: Digital input terminals (I2C controlled via 0x21, 0x22)

### Power Requirements

- **Board Power**: 12V DC input
- **Relay Voltage**: 12V DC output (for pumps)
- **Sensor Power**: 5V output available for sensors
- **I2C Logic**: 3.3V (handled by ESP32)

---

## 📊 Dosing System Integration

### Dashboard Integration

The dashboard uses ZMQ (port 5555) to send dosing commands:

```python
# Dashboard sends to ESP32 via serial
command = {
    "action": "activate",
    "pin": 27,
    "duration_ms": 5000,
    "channel": 1,
    "device_type": "pH+"
}
```

### Manual Control Programs

Each pump has a manual control program:
- `2 pH minus pump manual Pin 26 V4.py`
- `2 pH plus Pump Manual Pin 27 V4.py`
- `2p1 SOL A EC Pump Manual Pin 25 V4.py`
- `2p2 SOL B EC Pump Manual Pin 23 V4.py`
- `2p5 PP1 Manual.py` (Pin 14)

---

## ⚠️ Important Notes

### GPIO Pin Changes (ESP32-S3 Migration)

**Old Configuration** (ESP32 before migration):
- GPIO 4, 5 were used for I2C (SDA, SCL) ❌
- Relays controlled directly via GPIO pins ❌
- Various GPIO pins for pump control ❌

**New Configuration** (ESP32-S3 with relay wrapper):
- GPIO 9, 10 now used for I2C (SDA, SCL) ✅
- Relays controlled exclusively via I2C PCF8574 expanders ✅
- No direct GPIO control - all via I2C commands ✅
- GPIO logical identifiers maintained for code compatibility ✅

### Relay Control Behavior

- **Active LOW or HIGH**: Check KC868-A16 documentation (typically HIGH = ON)
- **Maximum Duration**: 60 seconds per activation (safety limit)
- **Concurrent Activation**: Multiple relays can be active simultaneously
- **Initialization**: All relays set to OFF on ESP32 boot

### Debugging

Enable relay control debug output:
```cpp
// relay_wrapper.h prints:
Serial.printf("Relay %s (0x24 bit %d) set to %s\n", ...);
```

---

## 🔍 Troubleshooting

### Relay Not Activating

1. **Check I2C Connection**: Verify GPIO 9 (SDA) and GPIO 10 (SCL) wiring for ESP32-S3
2. **Test I2C Devices**: Use I2C scanner to confirm 0x24 and 0x25 addresses
3. **Verify Power**: Ensure 12V power supply is connected to KC868-A16
4. **Serial Monitor**: Check for relay activation messages
5. **ESP32-S3 Board**: Confirm using ESP32-S3-WROOM-1U N16R8 with 16MB Flash

### I2C Communication Errors

```
Error: PCF8574 not responding at 0x24
Solution: Check I2C wiring, pull-up resistors (4.7kΩ recommended)
```

### Wrong Relay Activating

- Verify GPIO pin number in relay_mapping table
- Check physical wire connections to Y terminals
- Test with TEST_PIN commands

---

## 📝 Version History

- **v2.0** - Relay wrapper implementation (I2C control)
- **v1.0** - Direct GPIO control (deprecated)

---

## 🔗 Related Files

- `src/relay_wrapper.h` - Relay control wrapper implementation
- `src/main.cpp` - Main ESP32 firmware
- `src/globals.h` - GPIO pin definitions
- `platformio.ini` - PCF8574 library configuration
- `WIRING_SCHEME.md` - Complete system wiring diagram
