# KC868-A16 V3 Relay Mapping

## Hardware Configuration

### I2C Bus Configuration
- **SDA**: GPIO9
- **SCL**: GPIO10

### PCF8574 I2C Expanders
- **PCF8574 #1**: I2C Address **0x24** → Controls Relays **Y1-Y8**
- **PCF8574 #2**: I2C Address **0x25** → Controls Relays **Y9-Y16**

---

## Relay Mapping Tables

### PCF8574 #1 (Address 0x24) - Relays Y1-Y8

| PCF8574 Bit | Relay Terminal | I2C Address | Pin |
|-------------|----------------|-------------|-----|
| P0 (Bit 0) | **Y1** | 0x24 | 0 |
| P1 (Bit 1) | **Y2** | 0x24 | 1 |
| P2 (Bit 2) | **Y3** | 0x24 | 2 |
| P3 (Bit 3) | **Y4** | 0x24 | 3 |
| P4 (Bit 4) | **Y5** | 0x24 | 4 |
| P5 (Bit 5) | **Y6** | 0x24 | 5 |
| P6 (Bit 6) | **Y7** | 0x24 | 6 |
| P7 (Bit 7) | **Y8** | 0x24 | 7 |

### PCF8574 #2 (Address 0x25) - Relays Y9-Y16

| PCF8574 Bit | Relay Terminal | I2C Address | Pin |
|-------------|----------------|-------------|-----|
| P0 (Bit 0) | **Y9** | 0x25 | 0 |
| P1 (Bit 1) | **Y10** | 0x25 | 1 |
| P2 (Bit 2) | **Y11** | 0x25 | 2 |
| P3 (Bit 3) | **Y12** | 0x25 | 3 |
| P4 (Bit 4) | **Y13** | 0x25 | 4 |
| P5 (Bit 5) | **Y14** | 0x25 | 5 |
| P6 (Bit 6) | **Y15** | 0x25 | 6 |
| P7 (Bit 7) | **Y16** | 0x25 | 7 |

---

## Control Methods

### I2C Control via PCF8574

All relays are controlled exclusively via I2C through the two PCF8574 I/O expanders.

#### Example Code (Arduino/ESP32):

```cpp
#include "PCF8574.h"

// Initialize PCF8574 objects
PCF8574 pcf8574_1(0x24);  // Controls Y1-Y8
PCF8574 pcf8574_2(0x25);  // Controls Y9-Y16

void setup() {
    Wire.begin(9, 10);  // SDA=GPIO9, SCL=GPIO10
    
    pcf8574_1.begin();
    pcf8574_2.begin();
}

// Control relay Y1 (PCF8574 #1, bit 0)
pcf8574_1.digitalWrite(0, LOW);   // Turn Y1 ON (inverted logic)
pcf8574_1.digitalWrite(0, HIGH);  // Turn Y1 OFF

// Control relay Y13 (PCF8574 #2, bit 4)
pcf8574_2.digitalWrite(4, LOW);   // Turn Y13 ON (inverted logic)
pcf8574_2.digitalWrite(4, HIGH);  // Turn Y13 OFF
```

---

## Hardware Specifications

### Analog Inputs
- **A1**: GPIO4
- **A2**: GPIO6
- **A3**: GPIO7
- **A4**: GPIO5

### 1-Wire Interfaces (with pull-up resistors)
- **1-wire1**: GPIO47
- **1-wire2**: GPIO48
- **1-wire3**: GPIO38

### Free GPIO Pins (without pull-up resistors)
- **GPIO39**
- **GPIO40**
- **GPIO41**

### Ethernet (W5500)
- **CLK**: GPIO42
- **MOSI**: GPIO43
- **MISO**: GPIO44
- **CS**: GPIO15
- **INT**: GPIO2
- **RST**: GPIO1

### RS485
- **RXD**: GPIO17
- **TXD**: GPIO16

### SD Card (SPI)
- **MOSI**: GPIO12
- **SCK**: GPIO13
- **MISO**: GPIO14
- **CS**: GPIO11
- **CD** (Card Detect): GPIO21

### RF433MHz
- **Receiver**: GPIO8
- **Transmitter**: GPIO18

### Other I2C Devices
- **24C02 EEPROM**: Address 0x50
- **DS3231 RTC**: Address 0x68
- **SSD1306 Display**: Address 0x3C
- **Input Expander #1**: Address 0x21
- **Input Expander #2**: Address 0x22

---

## Important Notes

### Inverted Logic
The KC868-A16 uses **inverted relay control logic**:
- **LOW (0)** = Relay **ON** (energized)
- **HIGH (1)** = Relay **OFF** (de-energized)

### No Direct GPIO Control
All 16 relays are controlled **exclusively via I2C** through the PCF8574 expanders. The ESP32-S3 GPIO pins **cannot directly control the relays** - you must use I2C commands.

### Relay Wrapper Function
For code compatibility, you can use a wrapper function that translates GPIO-style calls to I2C:

```cpp
void relayWrite(int relay_number, int state) {
    // Invert logic: HIGH=OFF, LOW=ON
    int invertedState = (state == HIGH) ? LOW : HIGH;
    
    if (relay_number >= 1 && relay_number <= 8) {
        // Y1-Y8 on PCF8574 #1 (0x24)
        pcf8574_1.digitalWrite(relay_number - 1, invertedState);
    } else if (relay_number >= 9 && relay_number <= 16) {
        // Y9-Y16 on PCF8574 #2 (0x25)
        pcf8574_2.digitalWrite(relay_number - 9, invertedState);
    }
}

// Usage:
relayWrite(1, HIGH);   // Turn Y1 ON
relayWrite(13, HIGH);  // Turn Y13 ON
relayWrite(1, LOW);    // Turn Y1 OFF
```

---

## Wiring Reference

### Relay Terminals
Each relay has 3 terminals:
- **COM** (Common)
- **NO** (Normally Open) - Closed when relay is ON
- **NC** (Normally Closed) - Open when relay is ON

### Power Requirements
- **Relay Coil**: 12V DC (provided by board power supply)
- **Contact Rating**: 10A @ 250VAC / 10A @ 30VDC

---

*Document created: January 6, 2026*
*Board: Kincony KC868-A16 V3*
*Microcontroller: ESP32-S3-WROOM-1U N16R8*
