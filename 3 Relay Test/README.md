# KC868-A16 Relay Test Program

## Purpose
Standalone test program to verify PCF8574 relay control on KC868-A16 board, independent of main application logic.

## What it does
- Toggles relay Y11 ON/OFF every 5 seconds
- Tests inverted logic (HIGH=OFF, LOW=ON) by default
- Prints detailed status to serial monitor
- Allows switching between inverted/normal logic via serial command

## Hardware tested
- **Relay Y11** (PCF8574 at 0x25, bit 2) - EC Sol A pump
- I2C bus: GPIO 4 (SDA), GPIO 5 (SCL)
- PCF8574 addresses: 0x24 (Y1-Y8), 0x25 (Y9-Y16)

## How to use

### 1. Backup your main program
```bash
cd /Users/penutaco/Desktop/GitHub/1-NS-Manager-Basic-AI-KC868-A16-esp32-
mv src/main.cpp src/main.cpp.backup
```

### 2. Copy test program to main
```bash
cp "3 Relay Test/relay_test.cpp" src/main.cpp
```

### 3. Upload
```bash
platformio run --target upload
```

### 4. Open serial monitor
```bash
platformio device monitor --baud 115200
```

### 5. Observe
- Watch Y11 relay (11th relay on board)
- Listen for relay click sounds every 5 seconds
- Check if actuator connected to Y11 turns ON/OFF
- **Ignore LED indicators** - they may show opposite state

### 6. Test different logic mode (optional)
Type `i` in the serial monitor to toggle between inverted and normal logic modes.

### 7. Restore main program when done
```bash
mv src/main.cpp.backup src/main.cpp
platformio run --target upload
```

## Expected behavior

### With inverted logic (default):
- When program says "ON": PCF8574 output goes LOW → relay energizes → actuator runs
- When program says "OFF": PCF8574 output goes HIGH → relay de-energizes → actuator stops

### With normal logic (after typing 'i'):
- When program says "ON": PCF8574 output goes HIGH → relay energizes → actuator runs
- When program says "OFF": PCF8574 output goes LOW → relay de-energizes → actuator stops

## What to verify
1. **Relay clicks**: You should hear two clicks per 10-second cycle (one ON, one OFF)
2. **Actuator behavior**: Pump/valve should physically turn ON and OFF
3. **Which logic works**: If inverted works correctly, your main program needs inverted logic

## Troubleshooting

**No relay click heard:**
- Check I2C wiring (SDA=GPIO4, SCL=GPIO5)
- Verify PCF8574 I2C addresses with `i2cdetect` if available
- Check power supply to KC868-A16

**Relay clicks but wrong timing:**
- Try typing `i` to switch logic mode
- Compare actuator behavior with serial output

**Actuator stays ON all the time:**
- Wiring may be to NC (Normally Closed) instead of NO (Normally Open)
- Check terminal connections: use COM and NO terminals

**LEDs confusing:**
- Ignore LED indicators - they show inverted state on KC868-A16
- Focus only on actuator behavior and relay click sounds
