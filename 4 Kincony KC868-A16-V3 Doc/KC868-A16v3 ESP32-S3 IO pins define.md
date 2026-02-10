# KC868-A16v3 ESP32-S3 IO Pins Define

## Analog Inputs

| Pin Name | GPIO |
|----------|------|
| ANALOG_A1 | 4 |
| ANALOG_A2 | 6 |
| ANALOG_A3 | 7 |
| ANALOG_A4 | 5 |

---

## I2C Bus Configuration

### I2C Pins
- **SDA**: GPIO9
- **SCL**: GPIO10

### I2C Device Addresses

| Device | I2C Address |
|--------|-------------|
| Relay Controller #1 | 0x24 |
| Relay Controller #2 | 0x25 |
| Input Expander #1 | 0x21 |
| Input Expander #2 | 0x22 |
| 24C02 EEPROM | 0x50 |
| DS3231 RTC | 0x68 |
| SSD1306 Display | 0x3C |

---

## 1-Wire Interfaces

*Pull-up resistances on PCB*

| Interface | GPIO |
|-----------|------|
| 1-wire1 | GPIO47 |
| 1-wire2 | GPIO48 |
| 1-wire3 | GPIO38 |

---

## Free GPIO Pins

*Without pull-up resistance on PCB*

| Pin | GPIO |
|-----|------|
| free gpio-1 | GPIO39 |
| free gpio-2 | GPIO40 |
| free gpio-3 | GPIO41 |

---

## Ethernet (W5500) I/O Define

| Pin Function | GPIO |
|--------------|------|
| CLK | GPIO42 |
| MOSI | GPIO43 |
| MISO | GPIO44 |
| CS | GPIO15 |
| Interrupt | GPIO2 |
| Reset | GPIO1 |

---

## RS485

| Pin Function | GPIO |
|--------------|------|
| RXD | GPIO17 |
| TXD | GPIO16 |

---

## SD Card (SPI)

| Pin Function | GPIO |
|--------------|------|
| SPI-MOSI | GPIO12 |
| SPI-SCK | GPIO13 |
| SPI-MISO | GPIO14 |
| SPI-CS | GPIO11 |
| SD-CD (Card Detect) | GPIO21 |

---

## RF433MHz Wireless

| Function | GPIO |
|----------|------|
| RF433MHz Receiver | GPIO8 |
| RF433MHz Sender | GPIO18 |

---

## Additional Free GPIOs on PCB

*(Beside ESP32-S3 module)*

- GPIO39
- GPIO40
- GPIO41

---

*Document created: January 8, 2026*  
*Board: Kincony KC868-A16 V3*  
*Microcontroller: ESP32-S3-WROOM-1U N16R8*
