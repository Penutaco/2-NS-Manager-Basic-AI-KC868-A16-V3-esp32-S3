#ifndef GLOBALS_H
#define GLOBALS_H

// =============================================================================
// V3 Migration Notes:
// - GPIO 2,9,10,12-18,21 are reserved for V3 hardware (Ethernet, SD, RS485, RF433)
// - These LED_PIN defines are LOGICAL identifiers mapped to I2C relay control
// - Relays are controlled via PCF8574 I2C expanders (0x24, 0x25), NOT direct GPIO
// - Do NOT use ledcSetup/ledcAttachPin/pinMode on these pins
// =============================================================================

// Logical relay identifiers (mapped to I2C via relay_wrapper.h)
// PCF8574 #1 (0x24) - Y1-Y8
#define LED_PIN_2 2     // Y1 - V1 Valve (logical, I2C controlled)
#define LED_PIN_9 9     // Y2 - V2 Valve (logical, I2C controlled)
#define LED_PIN_10 10   // Y3 - V5 Valve (logical, I2C controlled)
#define LED_PIN_12 12   // Y4 - V6 Valve (logical, I2C controlled)
#define LED_PIN_13 13   // Y5 - PP2 Pump (logical, I2C controlled)
#define LED_PIN_14 14   // Y6 - PP1 Pump (logical, I2C controlled)
#define LED_PIN_15 15   // Y7 - V4 Valve (logical, I2C controlled)
#define LED_PIN_16 16   // Logical identifier for event handling (I2C controlled)
#define LED_PIN_17 17   // Logical identifier for event handling (I2C controlled)
#define LED_PIN_18 18   // Y8 - V3 Valve (logical, I2C controlled)

// PCF8574 #2 (0x25) - Y9-Y14
#define LED_PIN_19 19   // Y9 - Water Pump (logical, I2C controlled)
#define LED_PIN_23 23   // Y10 - EC Sol B (logical, I2C controlled)
#define LED_PIN_25 25   // Y11 - EC Sol A (logical, I2C controlled)
#define LED_PIN_26 26   // Y12 - pH- Pump (logical, I2C controlled)
#define LED_PIN_27 27   // Y13 - pH+ Pump (logical, I2C controlled)
#define LED_PIN_33 33   // Y14 - EC Sol C (logical, I2C controlled)

// Available GPIO for future use (not I2C controlled)
#define LED_PIN_21 21   // Available - was SD Card CD on V3 but not used
#define LED_PIN_22 22   // Available - free GPIO

// V3 Hardware-specific pins
#define DS18B20_PIN 47  // Temperature sensor (1-Wire with built-in pull-up)

// V3 Migration: PWM channels removed - relays use I2C, not PWM
// These defines kept for backwards compatibility but should not be used
// #define ledChannel2 0   // DEPRECATED - relay uses I2C
// #define ledChannel9 1   // DEPRECATED - relay uses I2C
// ... etc

// Sensor values
extern float actualVoltage;
extern float refVoltage;
extern float Absorbancia;
extern bool CalibrationReady;
extern float ConcentracionCu;
extern float pRecta[2];
extern float ecValue;  // Global EC value in mS/cm for serial output

// Calibration data
extern float ph_cal_points[2];  // Store pH calibration points
extern float nitrate_cal_points[2];  // Store Nitrate calibration points
extern int ph_cal_count;  // Add this line
extern float ph_cal_expected[2];  // Add this line

// Event control variables
extern bool isRef;        // Flag for Reference measurement
extern bool isMeasure;    // Flag for Sample measurement
extern float refValue;    // Store reference measurement
extern float measureValue; // Store sample measurement

// PRGCal and PRGSample counters
extern int currentPRGCalCount;  // Add this line
extern int currentPRGSampleCount;  // Add this line

#endif // GLOBALS_H
