/*
 * KC868-A16 Relay Test Program
 * Simple standalone test to verify PCF8574 relay control
 * Tests both inverted and non-inverted logic
 */

#include <Arduino.h>
#include <Wire.h>
#include "PCF8574.h"

// PCF8574 I2C addresses for KC868-A16
PCF8574 pcf8574_1(0x24);  // Controls relays Y1-Y8
PCF8574 pcf8574_2(0x25);  // Controls relays Y9-Y16

// Test configuration
const int TEST_RELAY_BIT = 2;      // Y11 is bit 2 on pcf8574_2
const int TEST_INTERVAL = 5000;    // 5 seconds ON, 5 seconds OFF
bool testInvertedLogic = true;     // Set to false to test non-inverted

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n\n=================================");
  Serial.println("KC868-A16 Relay Test Program");
  Serial.println("=================================");
  Serial.println("Testing Y11 (PCF8574 0x25, bit 2)");
  Serial.printf("Logic mode: %s\n", testInvertedLogic ? "INVERTED (HIGH=OFF, LOW=ON)" : "NORMAL (HIGH=ON, LOW=OFF)");
  Serial.println("=================================\n");

  // Initialize I2C
  Wire.begin(4, 5);  // SDA=GPIO4, SCL=GPIO5 for KC868-A16
  
  // Initialize PCF8574
  if (testInvertedLogic) {
    // Inverted: HIGH = relay OFF
    Serial.println("Initializing PCF8574 with HIGH (all relays OFF)...");
    pcf8574_1.begin(0xFF);
    pcf8574_2.begin(0xFF);
  } else {
    // Normal: LOW = relay OFF
    Serial.println("Initializing PCF8574 with LOW (all relays OFF)...");
    pcf8574_1.begin(0x00);
    pcf8574_2.begin(0x00);
  }
  
  Serial.println("Initialization complete.\n");
  Serial.println("Watch Y11 relay and connected actuator:");
  Serial.println("- Relay should toggle ON/OFF every 5 seconds");
  Serial.println("- LED indicator may show OPPOSITE of relay state (ignore LED)");
  Serial.println("- Focus on actuator behavior and relay click sounds\n");
}

void loop() {
  static unsigned long lastToggle = 0;
  static bool relayState = false;
  
  if (millis() - lastToggle >= TEST_INTERVAL) {
    lastToggle = millis();
    relayState = !relayState;
    
    // Determine actual PCF8574 output based on logic mode
    int pcfOutput;
    if (testInvertedLogic) {
      // Inverted: relay ON = PCF output LOW
      pcfOutput = relayState ? LOW : HIGH;
    } else {
      // Normal: relay ON = PCF output HIGH
      pcfOutput = relayState ? HIGH : LOW;
    }
    
    // Set the relay
    pcf8574_2.digitalWrite(TEST_RELAY_BIT, pcfOutput);
    
    // Print status
    Serial.println("----------------------------------");
    Serial.printf("Time: %lu ms\n", millis());
    Serial.printf("Relay Y11 commanded: %s\n", relayState ? "ON" : "OFF");
    Serial.printf("PCF8574 output sent: %s\n", pcfOutput == HIGH ? "HIGH" : "LOW");
    Serial.println("----------------------------------\n");
    
    if (relayState) {
      Serial.println(">>> Actuator should be ENERGIZED (running/open)");
      Serial.println(">>> You should hear a relay CLICK");
    } else {
      Serial.println(">>> Actuator should be DE-ENERGIZED (stopped/closed)");
      Serial.println(">>> You should hear a relay CLICK");
    }
    Serial.println();
  }
  
  // Optional: Add serial commands to change test mode
  if (Serial.available()) {
    char cmd = Serial.read();
    if (cmd == 'i' || cmd == 'I') {
      testInvertedLogic = !testInvertedLogic;
      Serial.printf("\n*** Logic mode changed to: %s ***\n\n", 
                    testInvertedLogic ? "INVERTED" : "NORMAL");
      // Re-initialize
      if (testInvertedLogic) {
        pcf8574_1.begin(0xFF);
        pcf8574_2.begin(0xFF);
      } else {
        pcf8574_1.begin(0x00);
        pcf8574_2.begin(0x00);
      }
    }
  }
}
