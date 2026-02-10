# KC868-A16-V3 Comprehensive Migration & GPIO Compatibility Guide

**Date**: January 7, 2026  
**Board**: Kincony KC868-A16-V3 (ESP32-S3-WROOM-1U N16R8 with 16MB Flash)  
**Document Purpose**: Complete GPIO compatibility analysis + relay mapping reference + implementation plan  
**Version**: 3.0 (Merged: GPIO analysis + relay mapping + implementation guide)

---

## Part 0: Hardware Architecture Overview

### I2C Configuration (ESP32-S3) ✅

- **I2C SDA Pin**: GPIO 9
- **I2C SCL Pin**: GPIO 10
- **PCF8574 #1 Address**: 0x24 (Controls Y1-Y8 relays)
- **PCF8574 #2 Address**: 0x25 (Controls Y9-Y16 relays)

### ⚠️ Critical Architecture Understanding

**GPIO Pin Numbers in Code** are **logical identifiers** used in the relay_wrapper code, NOT physical ESP32-S3 GPIO pins. All relay control happens exclusively via I2C (GPIO 9=SDA, GPIO 10=SCL). These logical GPIO numbers are translated to PCF8574 I2C commands by the relay wrapper.

**OLD (V1)**: Direct GPIO pin control for relays ❌  
**NEW (V3)**: I2C PCF8574 expander control only ✅

### Power Requirements

| Component | Voltage | Current | Notes |
|-----------|---------|---------|-------|
| Board Input | 12V DC | ~500mA base | All relays active ~2A |
| Relay Output | 12V DC | Up to 3A per relay | Max 48W per relay |
| Sensor Power | 5V | ~100-200mA | All sensors combined |
| I2C Logic | 3.3V | Automatic | Via internal regulator |

---

## Executive Summary

**Critical Finding**: There are **MULTIPLE GPIO CONFLICTS** between code usage and V3 hardware allocation.

### Conflicts Found: 12 🔴

| GPIO | Code Use | V3 Hardware | Conflict Level | Status |
|------|----------|------------|-----------------|--------|
| GPIO 2 | LED_PIN_2 (Y1 relay) | Ethernet INT | 🔴 CRITICAL | Pending |
| GPIO 4 | I2C SDA (Wire.begin) | ADS1115 A1 input | 🔴 CRITICAL | Pending |
| GPIO 5 | I2C SCL (Wire.begin) | ADS1115 A4 input | 🔴 CRITICAL | Pending |
| GPIO 12 | LED_PIN_12 (Y4 relay) | SD Card MOSI | 🟡 HIGH | Pending |
| GPIO 13 | LED_PIN_13 (Y5 relay) | SD Card SCK | 🟡 HIGH | Pending |
| GPIO 14 | LED_PIN_14 (Y6 relay) | SD Card MISO | 🟡 HIGH | Pending |
| GPIO 15 | LED_PIN_15 (Y7 relay) | Ethernet CS | 🟡 HIGH | Pending |
| GPIO 16 | LED_PIN_16 | RS485 TXD | 🟡 HIGH | Pending |
| GPIO 17 | LED_PIN_17 | RS485 RXD | 🟡 HIGH | Pending |
| GPIO 18 | LED_PIN_18 (Y8 relay) | RF433MHz TX | 🟡 HIGH | Pending |
| GPIO 21 | LED_PIN_21 | SD Card CD (detect) | 🟡 HIGH | Pending |
| GPIO 32 | DS18B20_PIN | **DOES NOT EXIST** | 🔴 CRITICAL | ✅ FIXED |

---

## Part 1: Relay Hardware Mapping

### Active Relays (In Use) - I2C Controlled

**Note**: GPIO Pin numbers below are **logical identifiers** for code compatibility, not physical ESP32-S3 pins. All controlled exclusively via I2C PCF8574 expanders.

| Relay | GPIO (Logical) | I2C Addr | Bit | Physical Terminal | Function | Description |
|-------|--------|----------|-----|-------------------|----------|-------------|
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
| **Y15** | — | 0x25 | 6 | Y15 | (Available) | Not yet assigned |
| **Y16** | — | 0x25 | 7 | Y16 | (Available) | Not yet assigned |

### Dosing System Integration

**Dashboard Dosing Commands** (via ZMQ port 5555 serial):
```json
{
  "action": "dose",
  "pin": 27,
  "duration_ms": 5000,
  "pump_type": "pH+",
  "channel": 1
}
```

**Valid relay control pins**: 27, 26, 25, 23, 33, 19, 14 (all controlled via I2C wrapper)  
**Maximum Duration**: 60 seconds per activation (safety limit)  
**Concurrent Operation**: Multiple relays can be active simultaneously

---

## Part 2: V3 Hardware GPIO Allocation (Complete Map)

### Already Used/Reserved GPIO Pins

| GPIO | Function | Hardware | Type | Notes |
|------|----------|----------|------|-------|
| **GPIO 1** | Ethernet RST | W5500 | Output | Reset line |
| **GPIO 2** | Ethernet INT | W5500 | Input/Interrupt | **CONFLICT**: Code uses as LED_PIN_2 |
| **GPIO 4** | Analog A1 | ADS1115 | I2C input | **CONFLICT**: Code uses as Wire SDA |
| **GPIO 5** | Analog A4 | ADS1115 | I2C input | **CONFLICT**: Code uses as Wire SCL |
| **GPIO 6** | Analog A3 | ADS1115 | I2C input | OK (ADS1115 only) |
| **GPIO 7** | Analog A2 | ADS1115 | I2C input | OK (ADS1115 only) |
| **GPIO 8** | RF433 RX | RF433MHz | Input | Receive only |
| **GPIO 9** | I2C SDA | PCF8574 | I2C | ✅ Correct for relays |
| **GPIO 10** | I2C SCL | PCF8574 | I2C | ✅ Correct for relays |
| **GPIO 11** | SD CS | SD Card | SPI | Chip select |
| **GPIO 12** | SD MOSI | SD Card | SPI | **CONFLICT**: Code uses as LED_PIN_12 |
| **GPIO 13** | SD SCK | SD Card | SPI | **CONFLICT**: Code uses as LED_PIN_13 |
| **GPIO 14** | SD MISO | SD Card | SPI | **CONFLICT**: Code uses as LED_PIN_14 |
| **GPIO 15** | Ethernet CS | W5500 | SPI | **CONFLICT**: Code uses as LED_PIN_15 |
| **GPIO 16** | RS485 TXD | RS485 | UART TX | **CONFLICT**: Code uses as LED_PIN_16 |
| **GPIO 17** | RS485 RXD | RS485 | UART RX | **CONFLICT**: Code uses as LED_PIN_17 |
| **GPIO 18** | RF433 TX | RF433MHz | Output | **CONFLICT**: Code uses as LED_PIN_18 |
| **GPIO 21** | SD CD | SD Card | Card Detect | **CONFLICT**: Code uses as LED_PIN_21 |
| **GPIO 42** | Ethernet CLK | W5500 | SPI | Clock |
| **GPIO 43** | Ethernet MOSI | W5500 | SPI | Data out |
| **GPIO 44** | Ethernet MISO | W5500 | SPI | Data in |

### Available GPIO Pins (Safe to Use)

| GPIO | Status | Type | Notes |
|------|--------|------|-------|
| **GPIO 19** | ✅ FREE | General Purpose | Dosing pump (EC dilution) |
| **GPIO 22** | ✅ FREE | General Purpose | Available for future use |
| **GPIO 23** | ✅ FREE | General Purpose | Dosing pump (EC Sol B) |
| **GPIO 25** | ✅ FREE | General Purpose | Dosing pump (EC Sol A) |
| **GPIO 26** | ✅ FREE | General Purpose | Dosing pump (pH-) |
| **GPIO 27** | ✅ FREE | General Purpose | Dosing pump (pH+) |
| **GPIO 33** | ✅ FREE | General Purpose | Dosing pump (EC Sol C) |
| **GPIO 38** | ✅ FREE | 1-Wire (with pull-up) | Can be used for temperature sensor |
| **GPIO 39** | ✅ FREE | General Purpose | Available for future use |
| **GPIO 40** | ✅ FREE | General Purpose | Available for future use |
| **GPIO 41** | ✅ FREE | General Purpose | Available for future use |
| **GPIO 47** | ✅ USED | 1-Wire (with pull-up) | **Temperature Sensor** (DS18B20) ✅ Correct |
| **GPIO 48** | ✅ FREE | 1-Wire (with pull-up) | Can be used for temperature sensor |

---

## Part 3: Code GPIO Usage Analysis

### Current I2C Configuration (WRONG ❌)

**In main.cpp line 241**:
```cpp
Wire.begin(4, 5);  // SDA on GPIO 4, SCL on GPIO 5 (KC868-A16 V1 pins)
```

**Problem**:
- GPIO 4 = ADS1115 Analog input A1 (NOT I2C) ❌
- GPIO 5 = ADS1115 Analog input A4 (NOT I2C) ❌
- Should use: GPIO 9 (SDA), GPIO 10 (SCL) ✅

**Impact**: 
- **I2C communication with PCF8574 relay controllers will FAIL completely**
- Conflicts with analog sensor inputs
- Direct conflict with V3 hardware I2C bus design

**Fix Required**: Change to `Wire.begin(9, 10);`

---

### LED/Relay Pin Definitions (Via PWM/Direct GPIO) - UNNECESSARY

**In globals.h** (example):
```cpp
#define LED_PIN_2 2    // Y1 - Ethernet INT conflict ❌
#define LED_PIN_9 9    // Y2 - I2C SDA conflict ❌
#define LED_PIN_10 10  // Y3 - I2C SCL conflict ❌
#define LED_PIN_12 12  // Y4 - SD Card MOSI conflict ❌
#define LED_PIN_13 13  // Y5 - SD Card SCK conflict ❌
#define LED_PIN_14 14  // Y6 - SD Card MISO conflict ❌
#define LED_PIN_15 15  // Y7 - Ethernet CS conflict ❌
#define LED_PIN_16 16  // Y8 - RS485 TXD conflict ❌
#define LED_PIN_17 17  // Y9 - RS485 RXD conflict ❌
#define LED_PIN_18 18  // Y10 - RF433 TX conflict ❌
#define LED_PIN_19 19  // Y11 - OK (free) ✅
#define LED_PIN_21 21  // Y12 - SD Card CD conflict ❌
#define LED_PIN_22 22  // Y13 - OK (free) ✅
#define LED_PIN_23 23  // Y14 - OK (free) ✅
#define LED_PIN_25 25  // Y15 - OK (free) ✅
#define LED_PIN_26 26  // Y16 - OK (free) ✅
#define LED_PIN_27 27  // Y17 - OK (free) ✅
#define LED_PIN_33 33  // Y18 - OK (free) ✅
#define DS18B20_PIN 32 // DOES NOT EXIST ❌ (FIXED to 47 ✅)
```

**Important Note**: These LED pins use `ledcAttachPin()` for PWM output channels. The physical GPIO pins must exist on the board. However, **relay control does NOT need these pins** - relays are controlled exclusively via I2C.

**In main.cpp lines 289-305**: Direct `pinMode()` and `ledcAttachPin()` calls configure these GPIO pins.

---

### Dosing Pump Pin Definitions (Direct GPIO - WRONG ❌)

**In main.cpp lines 90-95**:
```cpp
#define PH_PLUS_PIN 27        // ✅ GPIO 27 is FREE (good choice)
#define PH_MINUS_PIN 26       // ✅ GPIO 26 is FREE (good choice)
#define EC_PLUS_SOLA_PIN 25   // ✅ GPIO 25 is FREE (good choice)
#define EC_PLUS_SOLB_PIN 23   // ✅ GPIO 23 is FREE (good choice)
#define EC_PLUS_SOLC_PIN 33   // ✅ GPIO 33 is FREE (good choice)
#define EC_MINUS_H2O_PIN 19   // ✅ GPIO 19 is FREE (good choice)
```

**Status**: 
- GPIO pins (19, 23, 25, 26, 27, 33) are all **FREE** ✅ (No hardware conflicts)
- BUT they use direct `pinMode()` + `digitalWrite()` instead of `relayPinMode()` + `relayWrite()` ❌
- These pumps MUST use relay wrapper for I2C control (not direct GPIO)

**Fix Required**: Replace direct GPIO control with relay wrapper (separate issue from GPIO availability)

---

## Part 4: Detailed Conflict Analysis

### 🔴 CRITICAL - I2C Pin Conflict

**Issue**: Wire.begin(4, 5) conflicts with ADS1115 analog inputs

| Pin | Current Code | V3 Hardware | Conflict | Severity |
|-----|--------------|------------|----------|----------|
| **GPIO 4** | Wire SDA | ADS1115 A1 input | Direct conflict | 🔴 CRITICAL |
| **GPIO 5** | Wire SCL | ADS1115 A4 input | Direct conflict | 🔴 CRITICAL |

**Why It's Critical**:
- ADS1115 is the analog sensor interface for pH, EC, Nitrate, Light
- I2C PCF8574 relays **MUST** communicate via I2C to function
- Current code tries to use same GPIO pins for I2C clock/data AND analog sensor inputs
- **I2C relay communication will completely fail or interfere with analog sensor readings**
- **No relay control possible = system cannot operate**

**Solution**: Change to `Wire.begin(9, 10);` which are dedicated I2C pins on V3

---

### 🔴 CRITICAL - Ethernet Interrupt Conflict

**GPIO 2**: Code tries to use as LED/PWM output, but V3 uses for Ethernet INT

**Issue**:
```cpp
// main.cpp line 289
pinMode(LED_PIN_2, OUTPUT);  // Tries to configure as PWM output
ledcAttachPin(LED_PIN_2, ledChannel2);  // Attaches PWM channel

// But GPIO 2 is reserved for: W5500 Ethernet interrupt signal
```

**Impact**: 
- Ethernet INT interrupt cannot function if GPIO 2 is configured as PWM output
- Ethernet communication will be unreliable or fail
- If Ethernet is being used, system may hang or lose network connectivity

---

### 🟡 HIGH - SD Card Pin Conflicts

**Affected GPIOs**:
- GPIO 12: Code = LED_PIN_12 (PWM), Hardware = SD MOSI (SPI)
- GPIO 13: Code = LED_PIN_13 (PWM), Hardware = SD SCK (SPI)
- GPIO 14: Code = LED_PIN_14 (PWM), Hardware = SD MISO (SPI)
- GPIO 21: Code = LED_PIN_21 (PWM), Hardware = SD CD (Card Detect)

**Issue**: Cannot have both PWM LED control and SD card SPI communication on same pins

**Impact**: 
- SD card logging may fail if PWM is active on these pins
- Data corruption or card detection failure possible
- If logging is not used, impact is minimal

---

### 🟡 HIGH - RS485 & RF433 Conflicts

**RS485 (Serial Communication)**:
- GPIO 16: LED_PIN_16 (PWM) ↔ RS485 TXD (UART TX)
- GPIO 17: LED_PIN_17 (PWM) ↔ RS485 RXD (UART RX)

**RF433MHz (Wireless)**:
- GPIO 18: LED_PIN_18 (PWM) ↔ RF433 TX (RF output)

**Impact**: 
- RS485 serial communication will be unreliable
- RF433MHz transmission will be corrupted
- If these features not used, impact is minimal

---

### 🟢 OK - Dosing Pump Pins (GPIO Available)

**Good news**: Dosing pump GPIO choices are all FREE
- GPIO 19: FREE ✅
- GPIO 23: FREE ✅
- GPIO 25: FREE ✅
- GPIO 26: FREE ✅
- GPIO 27: FREE ✅
- GPIO 33: FREE ✅

**However**: They should use relay wrapper (I2C control), not direct GPIO

---

## Part 5: Summary of Issues by Type

### Issue Type 1: I2C Configuration (CRITICAL) 🔴

| File | Line | Current | Required | Severity | Impact |
|------|------|---------|----------|----------|--------|
| main.cpp | 241 | Wire.begin(4, 5) | Wire.begin(9, 10) | 🔴 CRITICAL | I2C relay control **BROKEN** |

**Why Critical**: Without correct I2C pins, relay system cannot function at all. Pump control, valve control, and all automated dosing will fail.

---

### Issue Type 2: Hardware Conflicts (HIGH) 🟡

| GPIO | Code Use | V3 Hardware | Potential Impact | Fix |
|------|----------|------------|------------------|-----|
| 2 | LED/PWM | Ethernet INT | Ethernet unreliable | Remove PWM config |
| 4 | Wire SDA | ADS1115 A1 | Analog sensor failure | Use correct pins |
| 5 | Wire SCL | ADS1115 A4 | Analog sensor failure | Use correct pins |
| 12-14 | LED/PWM | SD Card SPI | SD logging failure | Remove PWM config |
| 15 | LED/PWM | Ethernet CS | Ethernet SPI conflict | Remove PWM config |
| 16-18 | LED/PWM | RS485/RF433 | Comm failure | Remove PWM config |
| 21 | LED/PWM | SD Card CD | Card detection failure | Remove PWM config |

**Root Cause**: Code has unnecessary LED PWM definitions on GPIO pins that V3 uses for critical hardware.

**Options**:
1. **Remove** LED PWM control entirely (relays use I2C, don't need PWM)
2. **Use GPIO 39, 40, 41** for any LED PWM that's actually needed
3. **Clean up** LED pin definitions not used for relay control

---

### Issue Type 3: Control Method Architecture (MEDIUM) 🟡

| System | Current (Wrong) | Required (Right) | Impact |
|--------|-----------------|-----------------|--------|
| Relay Control | I2C via PCF8574 ✅ | I2C via PCF8574 ✅ | Working correctly |
| Dosing Pumps | Direct GPIO ❌ | I2C via relayWrite() | Partially working but inconsistent |
| LED Setup | Direct pinMode/ledcSetup | Should remove or relocate | Hardware conflicts |

**Insight**: Relay control architecture is correct (I2C), but peripheral GPIO setup causes conflicts.

---

## Part 6: Implementation Plan

### Priority 1: Fix I2C Configuration (CRITICAL - Must Do First)

**File**: `src/main.cpp`  
**Line**: ~241  
**Current Code**:
```cpp
Wire.begin(4, 5);  // SDA on GPIO 4, SCL on GPIO 5 (KC868-A16 V1 pins)
```

**Change To**:
```cpp
Wire.begin(9, 10);  // SDA on GPIO 9, SCL on GPIO 10 (V3 correct pins)
```

**Why**: 
- I2C relay control (PCF8574 at 0x24, 0x25) will not communicate
- Analog sensors (ADS1115 at 0x48) will not read correctly
- Entire system will be non-functional

**Testing After Fix**:
```bash
- Verify I2C devices detected (0x24, 0x25, 0x48)
- Test relay activation with TEST_PIN commands
- Verify analog sensors read correct values
```

---

### Priority 2: Remove Conflicting LED Pin Definitions (HIGH - Should Do Second)

**File**: `src/globals.h`  
**Action**: Comment out or remove these defines:
```cpp
// #define LED_PIN_2 2    // Conflicts with Ethernet INT
// #define LED_PIN_4 4    // (if exists) Conflicts with ADS1115
// #define LED_PIN_5 5    // (if exists) Conflicts with ADS1115
// #define LED_PIN_12 12  // Conflicts with SD MOSI
// #define LED_PIN_13 13  // Conflicts with SD SCK
// #define LED_PIN_14 14  // Conflicts with SD MISO
// #define LED_PIN_15 15  // Conflicts with Ethernet CS
// #define LED_PIN_16 16  // Conflicts with RS485 TXD
// #define LED_PIN_17 17  // Conflicts with RS485 RXD
// #define LED_PIN_18 18  // Conflicts with RF433 TX
// #define LED_PIN_21 21  // Conflicts with SD CD
```

**File**: `src/main.cpp`  
**Action**: Remove GPIO setup code

- **Remove lines ~260-275**: All `ledcSetup()` calls for PWM channels
- **Remove lines ~289-305**: All direct `pinMode()` calls on conflicting GPIO pins

**Why**: These LED PWM setups are unnecessary and cause hardware conflicts. Relays are controlled via I2C, not GPIO PWM.

---

### Priority 3: Update Dosing System (HIGH - If Using Dosing)

**File**: `src/DosingProgram.cpp`  
**Lines**: ~288-305  
**Current Code** (WRONG):
```cpp
void dosePump(int pin, unsigned long durationMs) {
    pinMode(pin, OUTPUT);  // Direct GPIO ❌
    digitalWrite(pin, HIGH);  // Activate pump
    delay(durationMs);
    digitalWrite(pin, LOW);  // Deactivate pump
}
```

**Change To** (RIGHT):
```cpp
void dosePump(int pin, unsigned long durationMs) {
    relayWrite(pin, HIGH);  // I2C relay control ✅
    delay(durationMs);
    relayWrite(pin, LOW);   // I2C relay control ✅
}
```

**Why**: V3 requires I2C control via relay wrapper for consistency and reliability

---

### Priority 4: Available GPIO for Future Use (OPTIONAL)

If you need LED indicators or other I/O:

**Safe GPIO pins for future use**:
- GPIO 22 (General purpose)
- GPIO 39 (General purpose)
- GPIO 40 (General purpose)
- GPIO 41 (General purpose)
- GPIO 38 (1-Wire if temperature sensor on GPIO 38 instead of 47)
- GPIO 48 (1-Wire if temperature sensor on GPIO 48 instead of 47)

---

## Part 7: Code Usage & Control Functions

### Relay Control Functions (Via relay_wrapper.h)

```cpp
// Include the wrapper
#include "relay_wrapper.h"

// Initialize all relays to OFF (run once in setup())
initializeRelays();

// Turn relay ON
relayWrite(27, HIGH);  // Activates Y13 (pH+ pump)

// Turn relay OFF
relayWrite(27, LOW);   // Deactivates Y13

// Configure pin mode (typically auto-handled by wrapper)
relayPinMode(27, OUTPUT);

// Query relay state (if supported by wrapper)
int state = relayRead(27);  // Get current state
```

### Serial Commands for Testing

```
TEST_PIN_27      - Test Y13 (pH+) relay for 10 seconds
TEST_PIN_26      - Test Y12 (pH-) relay for 10 seconds
TEST_PIN_25      - Test Y11 (EC Sol A) relay for 10 seconds
TEST_PIN_23      - Test Y10 (EC Sol B) relay for 10 seconds
TEST_PIN_33      - Test Y14 (EC Sol C) relay for 10 seconds
TEST_PIN_19      - Test Y9 (Water pump) relay for 10 seconds
RESET            - Turn all active relays OFF
INIT             - Initialize all relays to OFF
```

### JSON Dosing Commands (Dashboard Integration)

```json
{
  "action": "activate",
  "pin": 27,
  "duration_ms": 5000,
  "pump_type": "pH+",
  "channel": 1,
  "device_type": "dosing_pump"
}
```

---

## Part 8: Testing Checklist

### Pre-Compilation Tests
- [ ] Verify file changes syntax (no missing quotes/semicolons)
- [ ] Check that comments are properly formatted

### Post-Compilation Tests
- [ ] **Code Compiles**: No errors or warnings about GPIO conflicts

### Serial Port Tests (Monitor at 115200 baud)
- [ ] **I2C Scan**: Verify PCF8574 at 0x24, 0x25 detected
- [ ] **I2C Scan**: Verify ADS1115 at 0x48 detected
- [ ] **Relay Test Y1**: `TEST_PIN_2` activates Y1 valve
- [ ] **Relay Test Y4**: `TEST_PIN_12` activates Y4 valve
- [ ] **Relay Test Dosing**: `TEST_PIN_27` activates pH+ pump (5-10 seconds)

### Hardware Tests
- [ ] **Temperature Sensor**: GPIO 47 DS18B20 reads temperature correctly
- [ ] **Analog Sensors**: pH, EC, Nitrate, Light values reasonable
- [ ] **Relay Activation**: All 14 relays respond to control commands
- [ ] **Pump Operation**: All 6 dosing pumps activate/deactivate correctly
- [ ] **Ethernet** (if used): Network connectivity works
- [ ] **SD Card** (if used): File logging works
- [ ] **RS485** (if used): Serial communication works
- [ ] **RF433MHz** (if used): Wireless control works

### System Integration Tests
- [ ] Manual dosing via serial commands works
- [ ] Dashboard ZMQ commands work correctly
- [ ] Automatic pH/EC control logic functions
- [ ] No I2C communication errors in console
- [ ] All sensor readings stable and accurate

---

## Part 9: Troubleshooting Guide

### Relay Not Activating

**Symptom**: Relay doesn't turn on, pump doesn't activate

**Diagnosis**:
1. Check I2C communication first (this is the root cause 90% of time)
   ```bash
   - Verify GPIO 9 (SDA) and GPIO 10 (SCL) connections to PCF8574
   - Check I2C scan finds 0x24 and 0x25 addresses
   - Look for "I2C error" messages in console
   ```

2. Verify power supply
   ```bash
   - 12V power connected to KC868-A16 board
   - Voltage stable (11.8-12.2V acceptable)
   - Current capacity sufficient (~2A when all relays active)
   ```

3. Test specific relay
   ```bash
   - Serial command: TEST_PIN_27
   - Should activate Y13 (pH+ pump) for 10 seconds
   - Check physical pump for humming/movement
   ```

4. Check relay_wrapper configuration
   ```bash
   - Verify relay mapping table correct
   - Confirm GPIO pin number maps to correct relay
   - Check PCF8574 address (0x24 or 0x25)
   ```

---

### I2C Communication Errors

**Symptom**: Console shows "Wire error" or "I2C failed"

**Error Message**: `Error: PCF8574 not responding at 0x24`

**Diagnosis**:
```
1. Wire.begin() uses wrong pins
   - Verify: Wire.begin(9, 10);  // NOT Wire.begin(4, 5)
   
2. I2C wiring disconnected
   - Check GPIO 9 → PCF8574 SDA (pull-up to 3.3V)
   - Check GPIO 10 → PCF8574 SCL (pull-up to 3.3V)
   - Recommended: 4.7kΩ pull-up resistors
   
3. PCF8574 address mismatch
   - Verify address pins on PCF8574
   - Address 0x24: A0=L, A1=L, A2=L (Y1-Y8)
   - Address 0x25: A0=H, A1=L, A2=L (Y9-Y16)
   
4. Power supply to PCF8574
   - Verify 3.3V supply to expander IC
   - Check VCC and GND connections
   
5. Run I2C scanner
   - Load Arduino I2CScanner example
   - Should find addresses: 0x24, 0x25, 0x48 (ADS1115)
```

---

### Analog Sensors Not Reading

**Symptom**: pH, EC, Nitrate values stuck or invalid

**Error Message**: `Error: ADS1115 not responding at 0x48`

**Diagnosis**:
```
1. I2C pins wrong
   - Verify Wire.begin(9, 10);  // Correct V3 pins
   
2. ADS1115 power supply
   - Check 3.3V supply to ADS1115 IC
   - Check GND connection
   
3. I2C wiring to ADS1115
   - GPIO 9 → ADS1115 SDA (pull-up to 3.3V)
   - GPIO 10 → ADS1115 SCL (pull-up to 3.3V)
   
4. Check sensor connections
   - pH sensor → CH0 (ADS1115)
   - EC sensor → CH1 (ADS1115)
   - Nitrate sensor → CH2 (ADS1115)
   - Light sensor → CH3 (ADS1115)
   
5. Sensor calibration
   - Verify sensor offset and gain values
   - Check if sensors need recalibration
```

---

### Wrong Relay Activating

**Symptom**: Activating pump X actually activates pump Y

**Diagnosis**:
```
1. Check GPIO mapping
   - Verify gpio → relay mapping in relay_wrapper
   - Confirm physical wiring matches mapping
   
2. Verify I2C address
   - pH+ (pin 27) should address 0x25 bit 4
   - pH- (pin 26) should address 0x25 bit 3
   - Check PCF8574 address select pins (A0, A1, A2)
   
3. Test with serial commands
   - TEST_PIN_27 should activate only Y13
   - If other relay activates, check mapping table
   
4. Verify board wiring
   - Y13 terminal connected to correct pump
   - Check physical terminal connections on board
```

---

### Temperature Sensor Not Reading

**Symptom**: DS18B20 returns invalid temperature

**Error Message**: `Error: DS18B20 not found on GPIO 47`

**Diagnosis**:
```
1. GPIO 47 connection
   - Verify data line physically connected to GPIO 47
   - Check 4.7kΩ pull-up resistor to 3.3V
   - Ensure no shorts on signal line
   
2. OneWire library
   - Verify OneWire.h library installed
   - Check DS18B20 address matches code
   
3. Power supply
   - DS18B20 VCC → 3.3V or 5V (depending on model)
   - Check GND connection
   - Verify power stable
   
4. Hardware test
   - Power cycle board
   - Check if DS18B20 responds to onewire bus scan
   - Test with OneWire example sketch
   
5. Alternative GPIO
   - If GPIO 47 defective, try GPIO 38 or GPIO 48
   - Update #define DS18B20_PIN to new GPIO
```

---

### Board Not Powering On

**Symptom**: No LED, no serial output

**Diagnosis**:
```
1. Power supply check
   - Verify 12V DC power connected
   - Check voltage with multimeter
   - Confirm polarity correct (+ and -)
   
2. USB connection
   - If using USB programming: Check USB cable quality
   - Try different USB port on computer
   - Check if board detected in Device Manager
   
3. Fuse/Protection
   - Check if board has fuse that blew
   - Look for burnt components on board
   - Check for shorts from misconfigured GPIO
   
4. Bootloader
   - Try double-clicking reset button
   - Try holding BOOT button while plugging in
   - Flash bootloader recovery firmware
```

---

## Part 10: System Architecture Overview

### Board Sections & Terminals

1. **Relay Outputs (Y1-Y16)**
   - Connect pumps and valves here
   - 12V DC output, up to 3A per relay
   - Maximum 48W per relay

2. **Analog Inputs (CH1-CH4)**
   - ADS1115 (I2C) 4-channel ADC
   - CH1: pH sensor (0-3.3V)
   - CH2: EC sensor (0-3.3V)
   - CH3: Nitrate sensor (0-3.3V)
   - CH4: Light sensor (0-3.3V)

3. **1-Wire Bus (GPIO 38, 47, 48)**
   - DS18B20 temperature sensors
   - Currently using GPIO 47 ✅
   - Pull-up resistor: 4.7kΩ to 3.3V

4. **Digital Inputs (X1-X16)**
   - PCF8574 digital input expanders (if using)
   - Addresses: 0x21, 0x22 (optional)

5. **I2C Bus**
   - GPIO 9: SDA (Serial Data) ✅
   - GPIO 10: SCL (Serial Clock) ✅
   - Pull-up resistors: 4.7kΩ to 3.3V

### Control Flow Diagram

```
Dashboard (Python/ZMQ) or Serial Console
    ↓
ESP32-S3 Main Firmware
    ├→ Parse command (pump activation, sensor read, etc.)
    └→ Execute via I2C Bus:
        ├→ PCF8574 #1 (0x24) → Y1-Y8 Relays
        ├→ PCF8574 #2 (0x25) → Y9-Y16 Relays
        ├→ ADS1115 (0x48) → Analog Sensor Readings
        └→ OneWire (GPIO 47) → Temperature Reading
    
    ↓ Response
Dashboard / Serial Console shows results
```

### System Operating Modes

1. **Automatic pH/EC Control** (Primary)
   - Reads sensors continuously
   - Compares to setpoints
   - Activates dosing pumps via I2C relays
   - Safety timeouts (60 seconds max per pump)

2. **Manual Control** (via Dashboard)
   - Send ZMQ commands to activate pumps
   - Dashboard specifies duration
   - ESP32 handles timing and deactivation

3. **Serial Commands** (via Console)
   - TEST_PIN_XX for relay testing
   - RESET to deactivate all pumps
   - Manual diagnostics

---

## Part 11: Key Differences: V1 vs V3

### I2C Configuration

| Aspect | V1 (ESP32) | V3 (ESP32-S3) | Change |
|--------|-----------|--------------|--------|
| **I2C SDA Pin** | GPIO 4 | GPIO 9 | **MUST UPDATE** ⚠️ |
| **I2C SCL Pin** | GPIO 5 | GPIO 10 | **MUST UPDATE** ⚠️ |
| **PCF8574 #1** | 0x24 | 0x24 | ✅ Same |
| **PCF8574 #2** | 0x25 | 0x25 | ✅ Same |
| **ADS1115** | 0x48 | 0x48 | ✅ Same |
| **Relay Control** | I2C only | I2C only | ✅ Same architecture |

### Temperature Sensor

| Aspect | V1 (ESP32) | V3 (ESP32-S3) | Change |
|--------|-----------|--------------|--------|
| **GPIO Pin** | GPIO 32 ❌ | GPIO 47 ✅ | **ALREADY FIXED** ✅ |
| **Type** | DS18B20 | DS18B20 | ✅ Same |
| **Protocol** | OneWire | OneWire | ✅ Same |

### Dosing Pump Control

| Aspect | V1 (ESP32) | V3 (ESP32-S3) | Change |
|--------|-----------|--------------|--------|
| **Method** | Direct GPIO ❌ | I2C relay wrapper ✅ | **SHOULD UPDATE** |
| **Pin Setup** | Direct pinMode() ❌ | relayPinMode() ✅ | **SHOULD UPDATE** |
| **Activation** | Direct digitalWrite() ❌ | relayWrite() ✅ | **SHOULD UPDATE** |

### Hardware Conflicts

| V1 | V3 | Impact |
|----|----|----|
| GPIO 4/5 available | GPIO 4/5 used for ADS1115 | **I2C pins conflict** 🔴 |
| GPIO 32 exists | GPIO 32 does NOT exist | **Temp sensor removed** 🔴 |
| Various GPIO free | GPIO reserved for Ethernet/SD/RS485/RF433 | **LED conflicts** 🟡 |

---

## Summary & Immediate Action Items

### Issues Found: 12 GPIO conflicts
- **Critical Issues**: 3 (I2C pins, Ethernet conflict, Analog sensors)
- **High Issues**: 9 (LED/PWM on reserved GPIO)

### Status Summary

| Issue | Status | Action |
|-------|--------|--------|
| Temperature Sensor (GPIO 32→47) | ✅ FIXED | Already applied |
| I2C Configuration (4,5→9,10) | 🔴 **PENDING** | **FIX NOW** |
| LED Pin Conflicts (multiple GPIO) | 🟡 **PENDING** | Should fix |
| Dosing System (GPIO→I2C wrapper) | 🟡 **PENDING** | Should update |

### Next Steps (In Order)

1. **CRITICAL - Fix I2C Pins** (5 minutes)
   - Edit `src/main.cpp` line 241
   - Change: `Wire.begin(4, 5)` → `Wire.begin(9, 10)`
   - Recompile and test I2C communication

2. **CRITICAL - Test I2C Communication** (5-10 minutes)
   - Upload firmware
   - Open serial monitor at 115200 baud
   - Verify "I2C devices found: 0x24, 0x25, 0x48"
   - Run TEST_PIN commands to verify relays work

3. **HIGH - Clean Up LED Definitions** (10-15 minutes)
   - Comment out LED_PIN defines in globals.h for GPIO 2-21
   - Remove ledcSetup/pinMode calls in main.cpp
   - Recompile to verify no new errors

4. **OPTIONAL - Update Dosing System** (10-15 minutes)
   - Change dosePump() function to use relayWrite()
   - Update pump setup to use relayPinMode()
   - Test dosing pump activation

### Key Insight

**The LED PWM pins aren't needed for relay control** - relays are controlled exclusively via I2C. Removing the unnecessary LED GPIO configuration will eliminate most conflicts while maintaining full system functionality.

---

**Document Version**: 3.0 (Comprehensive Merged Guide)  
**Created**: January 7, 2026  
**Status**: Ready for implementation  
**Next Milestone**: Apply Priority 1 fix and test I2C communication
