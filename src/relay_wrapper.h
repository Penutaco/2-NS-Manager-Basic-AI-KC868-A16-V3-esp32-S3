#ifndef RELAY_WRAPPER_H
#define RELAY_WRAPPER_H

#include <Arduino.h>
#include "PCF8574.h"

// KC868-A16 Relay Control Wrapper
// This wrapper translates GPIO pin numbers to I2C relay control
// The KC868-A16 uses two PCF8574 I2C expanders to control 16 relays

// Relay mapping structure
struct RelayMap {
    int gpio_pin;           // Virtual GPIO pin number (for compatibility)
    uint8_t i2c_address;    // I2C address (0x24 or 0x25)
    uint8_t bit_number;     // Bit number (0-7)
    const char* name;       // Relay name for debugging
};

// External PCF8574 objects (initialized in main.cpp)
extern PCF8574 pcf8574_1;  // Address 0x24 - Controls relays Y1-Y8
extern PCF8574 pcf8574_2;  // Address 0x25 - Controls relays Y9-Y16

// Relay mapping table
// Maps your GPIO pin numbers to actual KC868-A16 relay channels
// CORRECTED to match actual hardware configuration
const RelayMap relay_mapping[] = {
    // GPIO Pin, I2C Addr, Bit, Name
    // PCF8574 #1 (0x24) - Controls Y1-Y8
    {2,  0x24, 0, "Y1-V1_H2O_AirVent"},      // GPIO 2  → Relay Y1 - V1 (H20/Air Vent)
    {9,  0x24, 1, "Y2-V2_Sample"},           // GPIO 9  → Relay Y2 - V2 (Sample/Comun)
    {10, 0x24, 2, "Y3-V5_pH4_In"},           // GPIO 10 → Relay Y3 - V5 (In pH=4/Comun)
    {12, 0x24, 3, "Y4-V6_pH7_In"},           // GPIO 12 → Relay Y4 - V6 (In pH=7/Comun)
    {13, 0x24, 4, "Y5-PP2_ToSensor"},        // GPIO 13 → Relay Y5 - PP2 (in to Sensor)
    {14, 0x24, 5, "Y6-PP1_Out"},             // GPIO 14 → Relay Y6 - PP1 (Out)
    {15, 0x24, 6, "Y7-V4_Tank"},             // GPIO 15 → Relay Y7 - V4 (OFF TANK ON V3)
    {18, 0x24, 7, "Y8-V3_pH_Switch"},        // GPIO 18 → Relay Y8 - V3 (OFF pH4.01 ON pH 6.86)
    
    // PCF8574 #2 (0x25) - Controls Y9-Y16
    {19, 0x25, 0, "Y9-H2O_Dilution"},        // GPIO 19 → Relay Y9 - Water Dilution
    {23, 0x25, 1, "Y10-EC_SolB"},            // GPIO 23 → Relay Y10 - EC+ Solution B
    {25, 0x25, 2, "Y11-EC_SolA"},            // GPIO 25 → Relay Y11 - EC+ Solution A
    {26, 0x25, 3, "Y12-pH_Minus"},           // GPIO 26 → Relay Y12 - pH- Dosing Pump
    {27, 0x25, 4, "Y13-pH_Plus"},            // GPIO 27 → Relay Y13 - pH+ Dosing Pump
    {33, 0x25, 5, "Y14-EC_SolC"},            // GPIO 33 → Relay Y14 - EC+ Solution C
    {-1, 0x25, 6, "Y15-Unused"},             // Relay Y15 unused
    {-1, 0x25, 7, "Y16-Unused"}              // Relay Y16 unused
};

const int RELAY_MAP_SIZE = sizeof(relay_mapping) / sizeof(RelayMap);

// Wrapper function to replace digitalWrite for relay pins
inline void relayWrite(int pin, int state) {
    // KC868-A16 uses inverted relay logic: HIGH=OFF, LOW=ON
    int invertedState = (state == HIGH) ? LOW : HIGH;
    
    // Search for this pin in the relay mapping
    for (int i = 0; i < RELAY_MAP_SIZE; i++) {
        if (relay_mapping[i].gpio_pin == pin) {
            // Found a relay pin
            if (relay_mapping[i].i2c_address == 0x24) {
                pcf8574_1.digitalWrite(relay_mapping[i].bit_number, invertedState);
                Serial.printf("Relay %s (0x24 bit %d) set to %s\n", 
                    relay_mapping[i].name, 
                    relay_mapping[i].bit_number,
                    state == HIGH ? "ON" : "OFF");
            } else if (relay_mapping[i].i2c_address == 0x25) {
                pcf8574_2.digitalWrite(relay_mapping[i].bit_number, invertedState);
                Serial.printf("Relay %s (0x25 bit %d) set to %s\n", 
                    relay_mapping[i].name, 
                    relay_mapping[i].bit_number,
                    state == HIGH ? "ON" : "OFF");
            }
            return;
        }
    }
    
    // Not a relay pin, use regular digitalWrite
    digitalWrite(pin, state);
}

// Wrapper function to replace pinMode for relay pins
inline void relayPinMode(int pin, int mode) {
    // Check if this is a relay pin
    for (int i = 0; i < RELAY_MAP_SIZE; i++) {
        if (relay_mapping[i].gpio_pin == pin) {
            // Relay pins are already configured as outputs in PCF8574
            // No need to set pinMode for I2C expander pins
            Serial.printf("Relay pin %d (%s) - pinMode ignored (I2C controlled)\n", 
                pin, relay_mapping[i].name);
            return;
        }
    }
    
    // Not a relay pin, use regular pinMode
    pinMode(pin, mode);
}

// Initialize all relays to OFF state
inline void initializeRelays() {
    Serial.println("Initializing KC868-A16 relays via I2C...");
    
    // CRITICAL: Must set pinMode FIRST, then begin(), then digitalWrite()
    // The begin() parameter is ignored by PCF8574 library!
    
    Serial.println("Step 1: Setting pinMode for all PCF8574 pins...");
    for (int i = 0; i < 8; i++) {
        pcf8574_1.pinMode(i, OUTPUT);
        pcf8574_2.pinMode(i, OUTPUT);
    }
    
    Serial.println("Step 2: Calling begin() to initialize I2C...");
    pcf8574_1.begin();
    pcf8574_2.begin();
    
    Serial.println("Step 3: Setting all relays to OFF (inverted logic: HIGH=OFF)...");
    // KC868-A16 uses inverted relay logic due to TLP181 optocouplers: HIGH=OFF, LOW=ON
    for (int i = 0; i < 8; i++) {
        pcf8574_1.digitalWrite(i, HIGH);
        pcf8574_2.digitalWrite(i, HIGH);
    }
    
    Serial.println("All relays initialized to OFF");
}

#endif // RELAY_WRAPPER_H
