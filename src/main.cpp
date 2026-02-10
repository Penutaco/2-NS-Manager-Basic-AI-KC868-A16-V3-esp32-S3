#include <Arduino.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Wire.h>                // Adicionar para I2C
#include <Adafruit_ADS1X15.h>    // Adicionar para ADS1115
#include "PCF8574.h"             // PCF8574 for relay control
#include "Event.h"  // Include events
#include "PRGCal.h"  // Include PRGCal events
#include "PRGSample.h"  // Include PRGSample events
#include "Photoresistor.h"  // Include Photoresistor processing
#include "ECSensor.h"  // Include EC Sensor processing
#include "relay_wrapper.h"  // Include relay control wrapper
#include "PHSensor.h"  // Include pH Sensor processing
#include "NitrateSensor.h"  // Include Nitrate Sensor processing
#include "globals.h"  // Include global variables
#include "DosingProgram.h"  // Include dosing program
#include <ArduinoJson.h>  // NOVO: Adicione este include

// Add a global reference to the current active event for use in other files
Event currentEvent = {0, 0, 0, 0, 0.0, 0.0, 0.0};  // Initialize with default values

// NEW: Add forward declaration for DS18B20 temperature function
float readDS18B20Temperature();
// Add forward declaration for dosing command handler
void handleDosingCommand(String command);

// Adicione estas declarações globais
float absorbance = 0.0;
float avgPhotoresistorVoltage = 0.0;
float avgECmScm = 0.0;  // Changed from avgECppm
float avgPHVoltage = 0.0;
float avgNitrateVoltage = 0.0;
float avgTemperature = 0.0;

// Define pins for sensors - leaving these since they're sensor-specific
#define PHOTORESISTOR_PIN 2  // Usar canal A2 do ADS1115
#define ECSENSOR_PIN 0       // Usar canal A0 do ADS1115  
#define PHSENSOR_PIN 1       // Usar canal A1 do ADS1115
#define NITRATESENSOR_PIN 3  // Usar canal A3 do ADS1115

// Após as declarações de pins
Adafruit_ADS1115 ads;  // Objeto do ADS1115

// PCF8574 objects for relay control (KC868-A16)
PCF8574 pcf8574_1(0x24);  // First I2C expander - Controls relays Y1-Y8
PCF8574 pcf8574_2(0x25);  // Second I2C expander - Controls relays Y9-Y16

// Define PWM properties
const int freq = 5000;
const int resolution = 8;

// Create OneWire and DS18B20 objects on DS18B20_PIN
OneWire oneWire(DS18B20_PIN);     // changed from LED_PIN_32
DallasTemperature sensors(&oneWire);

// Define global variables
unsigned long previousMillis = 0;
unsigned long photoMillis = 0;
unsigned long ledMillis = 0;
unsigned long sendMillis = 0;
int currentEventIndex = 0;
bool isPRGCal = true;  // Start with PRGCal

const int numSamples = 10;  // Changed from 40 to 10 samples
const int SAMPLE_INTERVAL = 1000;  // Changed to 1000ms (1 second) for desired pH sampling rate
float photoresistorSamples[numSamples];
float ecSamples[numSamples];  // Keeps the same name but will store mS/cm values
float phSamples[numSamples];
float nitrateSamples[numSamples];
float temperatureSamples[numSamples];
int sampleIndex = 0;

float ecVoltage = 0;
float phVoltage = 0;
float phValue = 0;
// Usar a variável global definida em globals.cpp (remover definição duplicada)
extern float ecValue;  // Use the global EC value defined in globals.cpp
float nitrateVoltage = 0;

ECSensor ecSensor(ECSENSOR_PIN);
ECSensor::ECReadings ecReadings;  // To store both voltage and PPM values

// Add a global or static variable to hold the pH value for serial output:
static float pHValueForSerial = NAN; // "inf" will be used if this is NaN

// Add a global variable to hold the EC value for serial output, similar to pH
static float ecValueForSerial = NAN; // "inf" will be used if this is NaN

// V3 Migration: Dosing pump pins defined in DosingProgram.h (single source of truth)
// Using: PH_PLUS_PIN=27, PH_MINUS_PIN=26, EC_PLUS_SOLA_PIN=25
//        EC_PLUS_SOLB_PIN=23, EC_PLUS_SOLC_PIN=33, EC_MINUS_H2O_PIN=19

// Enhanced serial format variables
static unsigned long cycle_id = 0;
static int current_stage = 1;
static String last_event_id = "";
static unsigned long last_dosing_time = 0;
static int cycles_since_dosing = 0;
static int error_count = 0;

// Dosing state tracking
struct DosingState {
    bool ph_within_tolerance = true;
    bool ec_within_tolerance = true;
    float target_ph = 6.0;
    float target_ec = 1.7;
    float ph_tolerance = 0.2;
    float ec_tolerance = 0.1;
    int system_health = 100;
};

DosingState dosing_state;

// Enhanced Serial Output Functions
void printSensorData(unsigned long timestamp, int event_num) {
    // Generate unique event ID
    String event_id = String(cycle_id) + "_PRGSample_" + String(event_num) + "_" + String(timestamp) + "_" + String(random(1000, 9999), HEX);
    
    // SENSOR format: timestamp,cycle_id,event_num,photo_volt,absorbance,concentration,ec_volt,ec_mscm,ph_volt,ph_value,nitrate_volt,temperature,stage,event_id
    Serial.printf("SENSOR,%lu,%lu,%d,%.5f,%.4f,%.2f,%.5f,%.2f,%.5f,%.2f,%.5f,%.2f,%d,%s\n",
        timestamp, cycle_id, event_num,
        avgPhotoresistorVoltage, absorbance, 0.0,  // concentration placeholder
        ecVoltage, isnan(ecValueForSerial) ? 0.0 : ecValueForSerial,
        avgPHVoltage, isnan(pHValueForSerial) ? 0.0 : pHValueForSerial,
        avgNitrateVoltage, avgTemperature,
        current_stage, event_id.c_str());
    
    last_event_id = event_id;
}

void printEventDetection(unsigned long timestamp, String event_type, int event_number, String action, float ph_val, float ec_val) {
    Serial.printf("EVENT,%lu,%lu,%s,%d,%s,%.2f,%.2f,15,0\n",
        timestamp, cycle_id, event_type.c_str(), event_number, action.c_str(), ph_val, ec_val);
}

void printSystemStatus(unsigned long timestamp) {
    // Get current dosing stage
    DosingStage current_dosing_stage = getCurrentStage();
    
    // Check tolerances using current stage targets
    bool ph_within_tolerance = abs(pHValueForSerial - current_dosing_stage.target_ph) <= current_dosing_stage.ph_tolerance;
    bool ec_within_tolerance = abs(ecValueForSerial - current_dosing_stage.target_ec) <= current_dosing_stage.ec_tolerance;
    
    // STATUS format: timestamp,cycle_id,stage,ph_within_tolerance,ec_within_tolerance,last_dosing_time,cycles_since_dosing,system_health,error_count
    Serial.printf("STATUS,%lu,%lu,%d,%s,%s,%lu,%d,%d,%d\n",
        timestamp, cycle_id, dosing_system.current_stage,
        ph_within_tolerance ? "true" : "false",
        ec_within_tolerance ? "true" : "false",
        dosing_system.last_dosing_time, dosing_system.cycles_since_dosing, 
        dosing_system.system_healthy ? 100 : 50, dosing_system.error_count);
}

void printDosingCalculation(unsigned long timestamp, float target_ph, float current_ph, float target_ec, float current_ec) {
    float ph_diff = target_ph - current_ph;
    float ec_diff = target_ec - current_ec;
    
    // Get current dosing stage for tolerances
    DosingStage stage = getCurrentStage();
    
    // Only log if dosing would be needed
    if (abs(ph_diff) > stage.ph_tolerance || abs(ec_diff) > stage.ec_tolerance) {
        String pump_type = "none";
        int pin_number = 0;
        float calculated_volume = 0.0;
        int dosing_time_ms = 0;
        
        if (abs(ph_diff) > stage.ph_tolerance) {
            if (ph_diff > 0) {
                pump_type = "ph_plus";
                pin_number = PH_PLUS_PIN;
                calculated_volume = calculateDosingVolume(current_ph, target_ph, dosing_system.ph_plus_coefficient);
            } else {
                pump_type = "ph_minus";
                pin_number = PH_MINUS_PIN;
                calculated_volume = calculateDosingVolume(current_ph, target_ph, dosing_system.ph_minus_coefficient);
            }
            calculated_volume *= stage.dosing_safety_factor;
            dosing_time_ms = volumeToDosingTime(calculated_volume);
        } else if (abs(ec_diff) > stage.ec_tolerance) {
            if (ec_diff > 0) {
                pump_type = "ec_sola";
                pin_number = EC_PLUS_SOLA_PIN;
                calculated_volume = calculateDosingVolume(current_ec, target_ec, dosing_system.ec_conductivity_coefficient);
            } else {
                pump_type = "h2o";
                pin_number = EC_MINUS_H2O_PIN;
                calculated_volume = calculateDosingVolume(current_ec, target_ec, dosing_system.h2o_dilution_coefficient);
            }
            calculated_volume *= stage.dosing_safety_factor;
            dosing_time_ms = volumeToDosingTime(calculated_volume);
        }
        
        // DOSING_CALC format with actual coefficients
        Serial.printf("DOSING_CALC,%lu,%lu,%.1f,%.2f,%.2f,%.1f,%.2f,%.2f,%.4f,%.2f,%.2f,%d,%s,%d,%d,%.1f,%d,1\n",
            timestamp, cycle_id, target_ph, current_ph, ph_diff, target_ec, current_ec, ec_diff,
            pump_type == "ph_plus" ? dosing_system.ph_plus_coefficient : 
            pump_type == "ph_minus" ? dosing_system.ph_minus_coefficient :
            pump_type == "ec_sola" ? dosing_system.ec_conductivity_coefficient :
            dosing_system.h2o_dilution_coefficient,
            calculated_volume, calculated_volume, dosing_time_ms, pump_type.c_str(), pin_number, 
            dosing_system.current_stage, stage.dosing_safety_factor, dosing_system.total_dosing_actions);
    } else {
        // No dosing needed
        Serial.printf("DOSING_CALC,%lu,%lu,%.1f,%.2f,%.2f,%.1f,%.2f,%.2f,0.0000,0.00,0.00,0,none,0,%d,1.0,%d,0\n",
            timestamp, cycle_id, target_ph, current_ph, ph_diff, target_ec, current_ec, ec_diff, 
            dosing_system.current_stage, dosing_system.total_dosing_actions);
    }
}

// Helper function to calculate average of array values
float calculateAverage(float values[], int count) {
    if (count == 0) return 0.0;
    
    float sum = 0.0;
    for (int i = 0; i < count; i++) {
        sum += values[i];
    }
    return sum / count;
}

void setup() {
  // Start serial communication at 115200 baud rate
  Serial.begin(115200);
  
  // Wait for USB CDC to connect (ESP32-S3 specific)
  delay(5000);  // 5 seconds for terminal to connect
  
  // Send boot messages repeatedly to catch terminal connection
  for (int i = 0; i < 10; i++) {
    Serial.println("========================================");
    Serial.println("ESP32-S3 BOOTING...");
    Serial.printf("Boot message #%d - millis=%lu\n", i, millis());
    Serial.println("========================================");
    delay(500);
  }

  // Send enhanced format notification
  Serial.println("=== ESP32 Enhanced Serial Format V1.0 ===");
  Serial.println("Formats: SENSOR, EVENT, STATUS, DOSING_CALC, CONVERSION, COEFFICIENT");
  Serial.println("Legacy format: Time, Photoresistor Voltage, Absorbance, Concentration, EC Voltage, EC mS/cm, pH Voltage, pH Value, Nitrate Voltage, Temperature");
  Serial.println("=== Starting Enhanced Data Stream ===");

  // Inicialização do I2C e ADS1115
  Serial.println("========================================");
  Serial.println("🔧 I2C INITIALIZATION");
  Serial.println("========================================");
  Serial.println("Configuration:");
  Serial.println("  - SDA: GPIO 9");
  Serial.println("  - SCL: GPIO 10");
  Serial.println("  - Board: KC868-A16 V3");
  Serial.println("Calling Wire.begin(9, 10)...");
  Wire.begin(9, 10);  // SDA on GPIO 9, SCL on GPIO 10 (KC868-A16 V3 I2C pins)
  Serial.println("✅ Wire.begin() completed");
  delay(100);  // Give I2C bus time to stabilize
  Serial.println("I2C bus stabilization delay complete");
  
  // I2C Scanner - detect all devices on the bus
  Serial.println("");
  Serial.println("========================================");
  Serial.println("🔍 I2C BUS SCANNER");
  Serial.println("========================================");
  Serial.println("Scanning addresses 0x01 to 0x7F...");
  int deviceCount = 0;
  for (byte address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    byte error = Wire.endTransmission();
    if (error == 0) {
      Serial.printf("  ✅ 0x%02X", address);
      if (address == 0x21) Serial.print(" - PCF8574 Input Expander #1");
      else if (address == 0x22) Serial.print(" - PCF8574 Input Expander #2");
      else if (address == 0x24) Serial.print(" - PCF8574 Relay Controller #1 (Y1-Y8)");
      else if (address == 0x25) Serial.print(" - PCF8574 Relay Controller #2 (Y9-Y16)");
      else if (address == 0x48) Serial.print(" - ADS1115 ADC (External Module)");
      else if (address == 0x50) Serial.print(" - EEPROM");
      else if (address == 0x68) Serial.print(" - RTC (Real-Time Clock)");
      else if (address == 0x3C) Serial.print(" - Display Controller");
      else Serial.print(" - Unknown Device");
      Serial.println();
      deviceCount++;
    }
  }
  Serial.println("----------------------------------------");
  if (deviceCount == 0) {
    Serial.println("❌ NO I2C DEVICES FOUND!");
    Serial.println("");
    Serial.println("Troubleshooting:");
    Serial.println("  1. Check I2C wiring:");
    Serial.println("     - SDA = GPIO 9");
    Serial.println("     - SCL = GPIO 10");
    Serial.println("  2. Expected onboard devices:");
    Serial.println("     - 0x24, 0x25 (PCF8574 relay controllers)");
    Serial.println("     - 0x21, 0x22 (PCF8574 input expanders)");
    Serial.println("     - 0x50 (EEPROM), 0x68 (RTC)");
    Serial.println("  3. External module (if connected):");
    Serial.println("     - 0x48 (ADS1115 ADC on I2C connector)");
    Serial.println("  4. Check power supply and connections");
  } else {
    Serial.printf("✅ Scan complete: %d device(s) detected\n", deviceCount);
  }
  Serial.println("========================================");
  Serial.println("");
  
  // Initialize PCF8574 relay controllers with correct sequence
  // Note: initializeRelays() now handles pinMode, begin(), and digitalWrite() in correct order
  Serial.println("========================================");
  Serial.println("🔌 PCF8574 RELAY INITIALIZATION");
  Serial.println("========================================");
  Serial.println("Initializing relay controllers at 0x24 and 0x25...");
  initializeRelays();
  Serial.println("✅ Relay controllers initialized");
  Serial.println("");
  
  // Initialize ADS1115 with graceful error handling
  Serial.println("========================================");
  Serial.println("📊 ADS1115 ADC INITIALIZATION");
  Serial.println("========================================");
  Serial.println("Attempting to initialize ADS1115 at address 0x48...");
  bool ads_success = ads.begin();
  if (!ads_success) {
    Serial.println("");
    Serial.println("❌ ADS1115 INITIALIZATION FAILED");
    Serial.println("");
    Serial.println("Possible causes:");
    Serial.println("  1. ADS1115 module not connected to I2C connector");
    Serial.println("  2. Wrong I2C address (check ADDR pin)");
    Serial.println("     - ADDR to GND  = 0x48 (default)");
    Serial.println("     - ADDR to VDD  = 0x49");
    Serial.println("     - ADDR to SDA  = 0x4A");
    Serial.println("     - ADDR to SCL  = 0x4B");
    Serial.println("  3. I2C wiring issue (SDA=GPIO9, SCL=GPIO10)");
    Serial.println("  4. Power supply issue (check 3.3V/5V)");
    Serial.println("");
    Serial.println("⚠️  CONTINUING with limited sensor functionality...");
    Serial.println("   Sensor readings will be invalid without ADS1115");
  } else {
    Serial.println("✅ ADS1115 initialized successfully at 0x48");
    Serial.println("   4-channel 16-bit ADC ready");
  }
  Serial.println("");
  Serial.println("Configuring ADS1115 gain: GAIN_ONE (±4.096V range)");
  ads.setGain(GAIN_ONE); // Configure gain regardless of init status
  Serial.println("✅ ADS1115 configuration complete");
  Serial.println("========================================");
  Serial.println("");

  // V3 Migration: Removed ledcSetup/ledcAttachPin/pinMode for relay GPIO pins
  // Relays are controlled exclusively via I2C (PCF8574), not GPIO PWM
  // GPIO 2,9,10,12-18,21 are reserved for V3 hardware (Ethernet, SD, RS485, RF433)
  
  // Only DS18B20 temperature sensor needs direct GPIO config
  pinMode(DS18B20_PIN, INPUT);  // GPIO 47 - Use INPUT since external 4.7kΩ pull-up is present

  // V3 Migration: Removed relayPinMode() calls - they are no-ops for I2C relays
  // PCF8574 expanders don't need pinMode configuration, I2C handles everything
  // Relay pin mapping (logical GPIO → I2C):
  //   PCF8574 #1 (0x24): Y1-Y8 = GPIO 2,9,10,12,13,14,15,18
  //   PCF8574 #2 (0x25): Y9-Y14 = GPIO 19,23,25,26,27,33

  // Initialize all relays to OFF via I2C
  relayWrite(LED_PIN_2, LOW);
  relayWrite(LED_PIN_9, LOW);
  relayWrite(LED_PIN_10, LOW);
  relayWrite(LED_PIN_12, LOW);
  relayWrite(LED_PIN_13, LOW);
  relayWrite(LED_PIN_14, LOW);
  relayWrite(LED_PIN_15, LOW);
  relayWrite(LED_PIN_16, LOW);
  relayWrite(LED_PIN_17, LOW);
  relayWrite(LED_PIN_18, LOW);
  relayWrite(LED_PIN_19, LOW);
  relayWrite(LED_PIN_23, LOW);
  relayWrite(LED_PIN_25, LOW);
  relayWrite(LED_PIN_26, LOW);
  relayWrite(LED_PIN_27, LOW);
  relayWrite(LED_PIN_33, LOW);

  // Reset event state
  currentEventIndex = 0;
  ledMillis = millis();  // Start timing from now
  
  Serial.println("Setup complete. Starting event sequence.");

  // Initialize all LEDs to OFF
  relayWrite(LED_PIN_2, LOW);
  relayWrite(LED_PIN_9, LOW);
  relayWrite(LED_PIN_10, LOW);
  
  // CRITICAL FIX FOR EVENT HANDLING
  // Reset event variables properly
  currentEventIndex = 0;
  ledMillis = millis();
  
  Serial.println("Setup complete - event sequence will begin with event #0");
  
  // CRITICAL FIX: Apply the first event CORRECTLY
  if (isPRGCal && numPRGcalEvents > 0) {
    Event firstEvent = PRGcalEvents[0];
    
    // Apply first event LED states
    relayWrite(LED_PIN_2, (firstEvent.ledState & (1 << 0)) ? HIGH : LOW);
    relayWrite(LED_PIN_9, (firstEvent.ledState & (1 << 1)) ? HIGH : LOW);
    relayWrite(LED_PIN_10, (firstEvent.ledState & (1 << 2)) ? HIGH : LOW);
    relayWrite(LED_PIN_12, (firstEvent.ledState & (1 << 3)) ? HIGH : LOW);
    relayWrite(LED_PIN_13, (firstEvent.ledState & (1 << 4)) ? HIGH : LOW);
    relayWrite(LED_PIN_14, (firstEvent.ledState & (1 << 5)) ? HIGH : LOW);
    relayWrite(LED_PIN_15, (firstEvent.ledState & (1 << 6)) ? HIGH : LOW);
    relayWrite(LED_PIN_16, (firstEvent.ledState & (1 << 7)) ? HIGH : LOW);
    relayWrite(LED_PIN_17, (firstEvent.ledState & (1 << 8)) ? HIGH : LOW);
    relayWrite(LED_PIN_18, (firstEvent.ledState & (1 << 9)) ? HIGH : LOW);
    relayWrite(LED_PIN_19, (firstEvent.ledState & (1 << 10)) ? HIGH : LOW);
    relayWrite(LED_PIN_23, (firstEvent.ledState & (1 << 13)) ? HIGH : LOW);
    relayWrite(LED_PIN_25, (firstEvent.ledState & (1 << 14)) ? HIGH : LOW);
    relayWrite(LED_PIN_26, (firstEvent.ledState & (1 << 15)) ? HIGH : LOW);
    relayWrite(LED_PIN_27, (firstEvent.ledState & (1 << 16)) ? HIGH : LOW);
    relayWrite(LED_PIN_33, (firstEvent.ledState & (1 << 18)) ? HIGH : LOW);
    
    // Handle special flags for first event
    if (firstEvent.refValue) {
      refVoltage = processPhotoresistor(PHOTORESISTOR_PIN);
      Serial.print("Initial reference voltage: ");
      Serial.println(refVoltage);
    }
    
    // CRITICAL CHANGE: Do NOT increment the event index yet - we stay at event 0 until its time elapses
    currentEventIndex = 0;
    
    Serial.print("Event #0 activated. LED state: ");
    Serial.println(firstEvent.ledState, BIN);
  }
  
  Serial.println("Setup complete. Event sequence will continue.");

  // Initialize DS18B20 temperature sensor
  sensors.begin();         // NEW: Begin DS18B20 sensor

  // Inicializar as variáveis de valor para serial
  pHValueForSerial = NAN;
  ecValueForSerial = NAN;
  
  // Initialize enhanced format variables
  cycle_id = 0;
  current_stage = 1;
  last_dosing_time = 0;
  cycles_since_dosing = 0;
  error_count = 0;
  dosing_state.system_health = 100;
  
  // Initialize dosing system
  initDosingSystem();
  
  // V3 Migration: Removed direct pinMode for dosing pumps (I2C handles via relay wrapper)
  // Ensure all pumps start OFF via I2C relay control
  relayWrite(PH_PLUS_PIN, LOW);
  relayWrite(PH_MINUS_PIN, LOW);
  relayWrite(EC_PLUS_SOLA_PIN, LOW);
  relayWrite(EC_PLUS_SOLB_PIN, LOW);
  relayWrite(EC_PLUS_SOLC_PIN, LOW);
  relayWrite(EC_MINUS_H2O_PIN, LOW);
}

void loop() {
    unsigned long currentMillis = millis();
    
    // Pequeno delay para garantir processamento adequado do buffer serial
    delay(5);

    // [1] Periodic sensor reading...
    if (currentMillis - photoMillis >= SAMPLE_INTERVAL) {
        photoMillis = currentMillis;
        // ...read sensors into samples...
        // Read and store the sensor values
        photoresistorSamples[sampleIndex] = processPhotoresistor(PHOTORESISTOR_PIN);
    auto ecData = ecSensor.processECSensor();  // Get both voltage and mS/cm
    ecVoltage = ecData.voltage; // Continuously update EC voltage
    // Do NOT update ecValueForSerial here! Only update in measurement event
    ecSamples[sampleIndex] = ecData.mS_cm; // For averaging/history only

        // Update pH measurements continuously:
        phSamples[sampleIndex] = processPHSensor(PHSENSOR_PIN);

        nitrateSamples[sampleIndex] = processNitrateSensor(NITRATESENSOR_PIN);
        temperatureSamples[sampleIndex] = readDS18B20Temperature();  // Now reads DS18B20 value

        sampleIndex = (sampleIndex + 1) % numSamples;
    }

    // [2] Periodic output...
    if (currentMillis - sendMillis >= 1000) {
        sendMillis = currentMillis;
        // ...calculate and print averages...
        // Calculate the averages
        avgPhotoresistorVoltage = 0;
        avgECmScm = 0;  // Changed from avgECppm
        avgPHVoltage = 0;
        avgNitrateVoltage = 0;
        avgTemperature = 0;

        for (int i = 0; i < numSamples; i++) {
            avgPhotoresistorVoltage += photoresistorSamples[i];
            avgECmScm += ecSamples[i];  // Changed from ecData.ppm
            avgPHVoltage += phSamples[i];
            avgNitrateVoltage += nitrateSamples[i];
            avgTemperature += temperatureSamples[i];
        }

        avgPhotoresistorVoltage /= numSamples;
        avgECmScm = calculateAverage(ecSamples, numSamples);  // Changed from avgECppm
        avgPHVoltage /= numSamples;
        avgNitrateVoltage /= numSamples;
        avgTemperature /= numSamples;

        // Calculate absorbance
        absorbance = calculateAbsorbance(avgPhotoresistorVoltage, refVoltage);

        // Get the current time in seconds
        float timeInSeconds = currentMillis / 1000.0;

        // Enhanced serial output with multiple formats
        unsigned long timestamp = currentMillis;
        
        // Increment cycle_id for each sensor reading
        cycle_id++;
        
        // Update current_stage from dosing system
        current_stage = dosing_system.current_stage;
        
        // Output sensor data in enhanced format
        printSensorData(timestamp, 5); // Event 5 is the measurement event
        
        // Print system status
        printSystemStatus(timestamp);
        
        // Get current dosing stage for targets
        DosingStage current_dosing_stage = getCurrentStage();
        
        // Print dosing calculation using actual stage targets
        printDosingCalculation(timestamp, current_dosing_stage.target_ph, 
                             isnan(pHValueForSerial) ? 0.0 : pHValueForSerial,
                             current_dosing_stage.target_ec, 
                             isnan(ecValueForSerial) ? 0.0 : ecValueForSerial);
        
        // Keep the original format for backward compatibility (commented out to avoid confusion)
        // Serial.printf("%.2f,%.5f,%.4f,%.2f,%.5f,%.2f,%.5f,%.2f,%.5f,%.2f,%.2f\n", 
        //               timeInSeconds, 
        //               avgPhotoresistorVoltage,  // Agora 5 casas decimais
        //               absorbance, 
        //               0.0,                      // Concentration 
        //               ecVoltage,               // EC voltage
        //               isnan(ecValueForSerial) ? 0.0 : ecValueForSerial,  // Now in mS/cm
        //               avgPHVoltage,            // Agora 5 casas decimais
        //               pHValueForSerial, 
        //               avgNitrateVoltage,       // Agora 5 casas decimais
        //               0.0, 
        //               avgTemperature);
        
        cycles_since_dosing++;
    }

    // [3] PRGCal vs PRGSample logic
    if (isPRGCal) {
        // -- Running PRGCal --
        if (numPRGcalEvents > 0) {
            Event currentEvent = PRGcalEvents[currentEventIndex];
            
            // Check if current event's duration has elapsed
            if (currentMillis - ledMillis >= currentEvent.waitTime) {
                // Move to next event
                currentEventIndex++;
                if (currentEventIndex >= numPRGcalEvents) {
                    // One full PRGCal sequence done
                    currentPRGCalCount++;
                    if (currentPRGCalCount >= x) {
                        // Switch to PRGSample
                        isPRGCal = false;
                        currentPRGCalCount = 0;  // Reset PRGCal count
                        currentEventIndex = 0;
                        Serial.print("Starting new PRGSample cycle (1 of ");
                        Serial.print(y);
                        Serial.println(")");

                        // [B] Immediately trigger Event #0 in PRGSample
                        if (numPRGsampleEvents > 0) {
                            Event firstEvent = PRGsampleEvents[0];
                            // ...set LED states from firstEvent...
                            relayWrite(LED_PIN_2, (firstEvent.ledState & (1 << 0)) ? HIGH : LOW);
                            relayWrite(LED_PIN_9, (firstEvent.ledState & (1 << 1)) ? HIGH : LOW);
                            relayWrite(LED_PIN_10, (firstEvent.ledState & (1 << 2)) ? HIGH : LOW);
                            relayWrite(LED_PIN_12, (firstEvent.ledState & (1 << 3)) ? HIGH : LOW);
                            relayWrite(LED_PIN_13, (firstEvent.ledState & (1 << 4)) ? HIGH : LOW);
                            relayWrite(LED_PIN_14, (firstEvent.ledState & (1 << 5)) ? HIGH : LOW);
                            relayWrite(LED_PIN_15, (firstEvent.ledState & (1 << 6)) ? HIGH : LOW);
                            relayWrite(LED_PIN_16, (firstEvent.ledState & (1 << 7)) ? HIGH : LOW);
                            relayWrite(LED_PIN_17, (firstEvent.ledState & (1 << 8)) ? HIGH : LOW);
                            relayWrite(LED_PIN_18, (firstEvent.ledState & (1 << 9)) ? HIGH : LOW);
                            relayWrite(LED_PIN_19, (firstEvent.ledState & (1 << 10)) ? HIGH : LOW);
                            relayWrite(LED_PIN_23, (firstEvent.ledState & (1 << 13)) ? HIGH : LOW);
                            relayWrite(LED_PIN_25, (firstEvent.ledState & (1 << 14)) ? HIGH : LOW);
                            relayWrite(LED_PIN_26, (firstEvent.ledState & (1 << 15)) ? HIGH : LOW);
                            relayWrite(LED_PIN_27, (firstEvent.ledState & (1 << 16)) ? HIGH : LOW);
                            relayWrite(LED_PIN_33, (firstEvent.ledState & (1 << 18)) ? HIGH : LOW);

                            Serial.print("PRGSample Event #0 activated at ");
                            Serial.print(currentMillis / 1000.0, 1);
                            Serial.print("s. Will last for ");
                            Serial.print(firstEvent.waitTime);
                            Serial.print("ms. LED state: ");
                            Serial.println(firstEvent.ledState, BIN);

                            ledMillis = currentMillis;
                        }
                    } else {
                        // Repeat PRGCal from event #0
                        currentEventIndex = 0;
                    }
                }

                // If still in PRGCal, activate the next event and log it
                if (isPRGCal) {
                    Event nextEvent = PRGcalEvents[currentEventIndex];
                    // Set LED states
                    relayWrite(LED_PIN_2, (nextEvent.ledState & (1 << 0)) ? HIGH : LOW);
                    relayWrite(LED_PIN_9, (nextEvent.ledState & (1 << 1)) ? HIGH : LOW);
                    relayWrite(LED_PIN_10, (nextEvent.ledState & (1 << 2)) ? HIGH : LOW);
                    relayWrite(LED_PIN_12, (nextEvent.ledState & (1 << 3)) ? HIGH : LOW);
                    relayWrite(LED_PIN_13, (nextEvent.ledState & (1 << 4)) ? HIGH : LOW);
                    relayWrite(LED_PIN_14, (nextEvent.ledState & (1 << 5)) ? HIGH : LOW);
                    relayWrite(LED_PIN_15, (nextEvent.ledState & (1 << 6)) ? HIGH : LOW);
                    relayWrite(LED_PIN_16, (nextEvent.ledState & (1 << 7)) ? HIGH : LOW);
                    relayWrite(LED_PIN_17, (nextEvent.ledState & (1 << 8)) ? HIGH : LOW);
                    relayWrite(LED_PIN_18, (nextEvent.ledState & (1 << 9)) ? HIGH : LOW);
                    relayWrite(LED_PIN_19, (nextEvent.ledState & (1 << 10)) ? HIGH : LOW);
                    relayWrite(LED_PIN_23, (nextEvent.ledState & (1 << 13)) ? HIGH : LOW);
                    relayWrite(LED_PIN_25, (nextEvent.ledState & (1 << 14)) ? HIGH : LOW);
                    relayWrite(LED_PIN_26, (nextEvent.ledState & (1 << 15)) ? HIGH : LOW);
                    relayWrite(LED_PIN_27, (nextEvent.ledState & (1 << 16)) ? HIGH : LOW);
                    relayWrite(LED_PIN_33, (nextEvent.ledState & (1 << 18)) ? HIGH : LOW);
                    // Log
                    Serial.print("PRGcal Event #");
                    Serial.print(currentEventIndex);
                    Serial.print(" activated at ");
                    Serial.print(currentMillis / 1000.0, 1);
                    Serial.print("s. Will last for ");
                    Serial.print(nextEvent.waitTime);
                    Serial.print("ms. LED state: ");
                    Serial.println(nextEvent.ledState, BIN);

                    // Verificar se é um ponto de calibração
                    if (nextEvent.measureValue == 1 && nextEvent.expectedPH > 0) {
                        Serial.print("PRGCal pH calibration point");
                        Serial.println();
                    }
                    
                    // Handle special ref/measure logic
                    if (nextEvent.refValue == 1) {
                        refVoltage = processPhotoresistor(PHOTORESISTOR_PIN);
                        Serial.print("Reference voltage set: ");
                        Serial.println(refVoltage);
                    }
                    
                    if (nextEvent.measureValue == 1) {
                        phVoltage = processPHSensor(PHSENSOR_PIN);
                        if (nextEvent.expectedPH > 0) {
                            // Scenario 1: store voltage + calibration point, do not convert
                            if (ph_cal_count < 2) {
                                ph_cal_points[ph_cal_count] = phVoltage;
                                ph_cal_expected[ph_cal_count] = nextEvent.expectedPH; // Store expected pH
                                ph_cal_count++;
                                
                                // Preparar a mensagem para a coluna Event Info
                                String eventMessage = "PRGCal pH calibration point: time " + 
                                                     String(currentMillis) + " ms, " + 
                                                     String(phVoltage, 3) + " V, pH: " + 
                                                     String(nextEvent.expectedPH, 2);
                                
                                // Enviar uma única linha com dados + mensagem
                                Serial.printf("%.2f,%.5f,%.4f,%.2f,%.5f,%.2f,%.5f,%.2f,%.5f,%.2f,%.2f,%s\n", 
                                              currentMillis / 1000.0, 
                                              avgPhotoresistorVoltage,
                                              absorbance, 
                                              0.0,                 // Concentration placeholder
                                              ecReadings.voltage, 
                                              ecReadings.mS_cm,  // Changed from ecReadings.ppm
                                              phVoltage,           // Changed from %.2f to %.5f
                                              nextEvent.expectedPH,  // Usar o pH esperado
                                              avgNitrateVoltage, 
                                              0.0,                 // Nitrate value placeholder
                                              avgTemperature,
                                              eventMessage.c_str());
                            } else if (ph_cal_count >= 2) {
                                // Reset ph_cal_count and overwrite previous calibration points
                                ph_cal_count = 0;
                                ph_cal_points[ph_cal_count] = phVoltage;
                                ph_cal_expected[ph_cal_count] = nextEvent.expectedPH; // Store expected pH
                                ph_cal_count++;
                                
                                // Formato modificado para corresponder ao padrão
                                Serial.print("PRGCal pH calibration point: time ");
                                Serial.print(currentMillis);  // Tempo atual em ms
                                Serial.print(" ms, ");
                                Serial.print(phVoltage, 3);
                                Serial.print(" V, pH: ");
                                Serial.println(nextEvent.expectedPH, 2);

                                // Adicionar esta linha para enviar também em formato CSV
                                Serial.printf("%.2f,%.2f,%.4f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f\n", 
                                              currentMillis / 1000.0, 
                                              avgPhotoresistorVoltage,
                                              absorbance, 
                                              0.0,                 // Concentration placeholder
                                              ecReadings.voltage, 
                                              ecReadings.mS_cm,    // Changed from ecReadings.ppm
                                              phVoltage,           // Usar o valor recém-medido 
                                              nextEvent.expectedPH,  // Usar o pH esperado
                                              avgNitrateVoltage, 
                                              0.0,                 // Nitrate value placeholder
                                              avgTemperature);
                            }
                            pHValueForSerial = nextEvent.expectedPH; // Store expected pH for serial
                        } else if (nextEvent.expectedPH == -1) {
                            // Scenario 2: convert using existing calibrations, don't store
                            float localPh = convertPHSensorVoltageToValue(phVoltage);
                            pHValueForSerial = localPh;
                        }
                    } else {
                        // Scenario 3: measureValue = 0 => read voltage, set pHValue to Inf
                        phVoltage = processPHSensor(PHSENSOR_PIN);
                        pHValueForSerial = INFINITY;
                    }

                    // Process EC sensor
                    ECSensor::ECReadings ecReadings = ecSensor.processECSensor();
                    ecVoltage = ecReadings.voltage;
                    ecValue = ecReadings.mS_cm; // Changed from ecReadings.ppm to mS_cm
                    
                    ledMillis = currentMillis;
                }
            }
        }
    } else { // This is the PRGSample section
        if (numPRGsampleEvents > 0) {
            Event currentEvent = PRGsampleEvents[currentEventIndex];

            // Check if current event's duration has elapsed
            if (currentMillis - ledMillis >= currentEvent.waitTime) {
                currentEventIndex++;
                if (currentEventIndex >= numPRGsampleEvents) {
                    Serial.println("PRGSample sequence complete.");
                    currentPRGSampleCount++;
                    currentEventIndex = 0; 
                    
                    // Handle next PRGSample cycle
                    if (currentPRGSampleCount < y) {
                        // Apply Event #0 of the new PRGSample cycle
                        Event firstEvent = PRGsampleEvents[0];
                        
                        // IMPORTANT: Ensure currentEventIndex is properly reset to 0 here
                        currentEventIndex = 0;
                        
                        // Then set LED states as before
                        relayWrite(LED_PIN_2, (firstEvent.ledState & (1 << 0)) ? HIGH : LOW);
                        relayWrite(LED_PIN_9, (firstEvent.ledState & (1 << 1)) ? HIGH : LOW);
                        relayWrite(LED_PIN_10, (firstEvent.ledState & (1 << 2)) ? HIGH : LOW);
                        relayWrite(LED_PIN_12, (firstEvent.ledState & (1 << 3)) ? HIGH : LOW);
                        relayWrite(LED_PIN_13, (firstEvent.ledState & (1 << 4)) ? HIGH : LOW);
                        relayWrite(LED_PIN_14, (firstEvent.ledState & (1 << 5)) ? HIGH : LOW);
                        relayWrite(LED_PIN_15, (firstEvent.ledState & (1 << 6)) ? HIGH : LOW);
                        relayWrite(LED_PIN_16, (firstEvent.ledState & (1 << 7)) ? HIGH : LOW);
                        relayWrite(LED_PIN_17, (firstEvent.ledState & (1 << 8)) ? HIGH : LOW);
                        relayWrite(LED_PIN_18, (firstEvent.ledState & (1 << 9)) ? HIGH : LOW);
                        relayWrite(LED_PIN_19, (firstEvent.ledState & (1 << 10)) ? HIGH : LOW);
                        relayWrite(LED_PIN_23, (firstEvent.ledState & (1 << 13)) ? HIGH : LOW);
                        relayWrite(LED_PIN_25, (firstEvent.ledState & (1 << 14)) ? HIGH : LOW);
                        relayWrite(LED_PIN_26, (firstEvent.ledState & (1 << 15)) ? HIGH : LOW);
                        relayWrite(LED_PIN_27, (firstEvent.ledState & (1 << 16)) ? HIGH : LOW);
                        relayWrite(LED_PIN_33, (firstEvent.ledState & (1 << 18)) ? HIGH : LOW);
                        
                        // Full logging to match other events
                        Serial.print("Starting new PRGSample cycle (");
                        Serial.print(currentPRGSampleCount + 1);
                        Serial.print(" of ");
                        Serial.print(y);
                        Serial.println(")");
                        Serial.print("PRGSample Event #0 activated at ");
                        Serial.print(currentMillis / 1000.0, 1);
                        Serial.print("s. Will last for ");
                        Serial.print(firstEvent.waitTime);
                        Serial.print("ms. LED state: ");
                        Serial.println(firstEvent.ledState, BIN);
                    }
                    
                    if (currentPRGSampleCount >= y) {
                        // Existing code for switching back to PRGCal
                        Serial.println("Switching back to PRGCal sequence...");
                        isPRGCal = true;
                        currentPRGSampleCount = 0;  // Reset PRGSample count

                        // [C] Immediately trigger Event #0 in PRGCal
                        if (numPRGcalEvents > 0) {
                            Event firstEvent = PRGcalEvents[0];
                            // ...set LED states from firstEvent...
                            relayWrite(LED_PIN_2, (firstEvent.ledState & (1 << 0)) ? HIGH : LOW);
                            relayWrite(LED_PIN_9, (firstEvent.ledState & (1 << 1)) ? HIGH : LOW);
                            relayWrite(LED_PIN_10, (firstEvent.ledState & (1 << 2)) ? HIGH : LOW);
                            relayWrite(LED_PIN_12, (firstEvent.ledState & (1 << 3)) ? HIGH : LOW);
                            relayWrite(LED_PIN_13, (firstEvent.ledState & (1 << 4)) ? HIGH : LOW);
                            relayWrite(LED_PIN_14, (firstEvent.ledState & (1 << 5)) ? HIGH : LOW);
                            relayWrite(LED_PIN_15, (firstEvent.ledState & (1 << 6)) ? HIGH : LOW);
                            relayWrite(LED_PIN_16, (firstEvent.ledState & (1 << 7)) ? HIGH : LOW);
                            relayWrite(LED_PIN_17, (firstEvent.ledState & (1 << 8)) ? HIGH : LOW);
                            relayWrite(LED_PIN_18, (firstEvent.ledState & (1 << 9)) ? HIGH : LOW);
                            relayWrite(LED_PIN_19, (firstEvent.ledState & (1 << 10)) ? HIGH : LOW);
                            relayWrite(LED_PIN_23, (firstEvent.ledState & (1 << 13)) ? HIGH : LOW);
                            relayWrite(LED_PIN_25, (firstEvent.ledState & (1 << 14)) ? HIGH : LOW);
                            relayWrite(LED_PIN_26, (firstEvent.ledState & (1 << 15)) ? HIGH : LOW);
                            relayWrite(LED_PIN_27, (firstEvent.ledState & (1 << 16)) ? HIGH : LOW);
                            relayWrite(LED_PIN_33, (firstEvent.ledState & (1 << 18)) ? HIGH : LOW);

                            Serial.print("PRGcal Event #0 activated at ");
                            Serial.print(currentMillis / 1000.0, 1);
                            Serial.print("s. Will last for ");
                            Serial.print(firstEvent.waitTime);
                            Serial.print("ms. LED state: ");
                            Serial.println(firstEvent.ledState, BIN);

                            ledMillis = currentMillis;
                        }
                    }
                    
                } else {
                    // Activate and log the next PRGSample event
                    Event nextEvent = PRGsampleEvents[currentEventIndex];
                    
                    // Set LED states
                    relayWrite(LED_PIN_2, (nextEvent.ledState & (1 << 0)) ? HIGH : LOW);
                    relayWrite(LED_PIN_9, (nextEvent.ledState & (1 << 1)) ? HIGH : LOW);
                    relayWrite(LED_PIN_10, (nextEvent.ledState & (1 << 2)) ? HIGH : LOW);
                    relayWrite(LED_PIN_12, (nextEvent.ledState & (1 << 3)) ? HIGH : LOW);
                    relayWrite(LED_PIN_13, (nextEvent.ledState & (1 << 4)) ? HIGH : LOW);
                    relayWrite(LED_PIN_14, (nextEvent.ledState & (1 << 5)) ? HIGH : LOW);
                    relayWrite(LED_PIN_15, (nextEvent.ledState & (1 << 6)) ? HIGH : LOW);
                    relayWrite(LED_PIN_16, (nextEvent.ledState & (1 << 7)) ? HIGH : LOW);
                    relayWrite(LED_PIN_17, (nextEvent.ledState & (1 << 8)) ? HIGH : LOW);
                    relayWrite(LED_PIN_18, (nextEvent.ledState & (1 << 9)) ? HIGH : LOW);
                    relayWrite(LED_PIN_19, (nextEvent.ledState & (1 << 10)) ? HIGH : LOW);
                    relayWrite(LED_PIN_23, (nextEvent.ledState & (1 << 13)) ? HIGH : LOW);
                    relayWrite(LED_PIN_25, (nextEvent.ledState & (1 << 14)) ? HIGH : LOW);
                    relayWrite(LED_PIN_26, (nextEvent.ledState & (1 << 15)) ? HIGH : LOW);
                    relayWrite(LED_PIN_27, (nextEvent.ledState & (1 << 16)) ? HIGH : LOW);
                    relayWrite(LED_PIN_33, (nextEvent.ledState & (1 << 18)) ? HIGH : LOW);
                    
                    // ADD THIS CODE: Process pH and EC measurement in PRGSample
                    if (nextEvent.measureValue == 1) {
                        // If this is a measurement event (expectedPH/EC == -1.0)
                        if (nextEvent.expectedPH == -1.0) {
                            float phVoltageReading = processPHSensor(PHSENSOR_PIN);
                            pHValueForSerial = convertPHSensorVoltageToValue(phVoltageReading);
                            
                            // Enhanced event logging
                            printEventDetection(currentMillis, "PRGSample", currentEventIndex, 
                                              "pH_measurement", pHValueForSerial, 
                                              isnan(ecValueForSerial) ? 0.0 : ecValueForSerial);
                            
                            Serial.print("PRGSample pH measurement");
                            Serial.println();
                        }
                        
                        // Add EC measurement processing
                        if (nextEvent.expectedEC == -1.0) {
                            auto ecDataReading = ecSensor.processECSensor();
                            ecVoltage = ecDataReading.voltage;
                            ecValueForSerial = ecDataReading.mS_cm; // Use a variável específica para serialização
                            
                            // Enhanced event logging
                            printEventDetection(currentMillis, "PRGSample", currentEventIndex, 
                                              "EC_measurement", 
                                              isnan(pHValueForSerial) ? 0.0 : pHValueForSerial, 
                                              ecValueForSerial);
                            
                            Serial.print("PRGSample EC measurement");
                            Serial.println();
                        }
                    }
                    
                    // DOSING INTEGRATION: Trigger dosing on the event AFTER measurements
                    // Event #5 takes measurements, Event #14 triggers dosing based on those measurements
                    if (currentEventIndex == 14) {
                        printEventDetection(currentMillis, "PRGSample", 14, "dosing_trigger",
                                          isnan(pHValueForSerial) ? 0.0 : pHValueForSerial,
                                          isnan(ecValueForSerial) ? 0.0 : ecValueForSerial);
                        
                        // Use measurements from previous event (Event #5) to make dosing decisions
                        if (!isnan(pHValueForSerial) && !isnan(ecValueForSerial)) {
                            Serial.println("=== DOSING CHECK TRIGGERED BY EVENT #14 ===");
                            Serial.printf("Using measurements from Event #5: pH=%.2f, EC=%.2f\n", 
                                        pHValueForSerial, ecValueForSerial);
                            
                            bool dosing_occurred = checkAndDose(cycle_id, pHValueForSerial, ecValueForSerial);
                            
                            if (dosing_occurred) {
                                Serial.printf("Dosing completed for cycle %d\n", cycle_id);
                            } else {
                                Serial.printf("No dosing needed for cycle %d\n", cycle_id);
                            }
                        } else {
                            Serial.println("Warning: pH or EC values not available for dosing check");
                            Serial.printf("Debug: pHValueForSerial=%f, ecValueForSerial=%f\n", 
                                        pHValueForSerial, ecValueForSerial);
                        }
                    }
                    
                    // Log
                    Serial.print("PRGSample Event #");
                    Serial.print(currentEventIndex);
                    Serial.print(" activated at ");
                    Serial.print(currentMillis / 1000.0, 1);
                    Serial.print("s. Will last for ");
                    Serial.print(nextEvent.waitTime);
                    Serial.print("ms. LED state: ");
                    Serial.println(nextEvent.ledState, BIN);
                }
                ledMillis = currentMillis;
            }
        }
    }

    // [4] Listen for serial commands...
    if (Serial.available() > 0) {
        String command = Serial.readStringUntil('\n');
        command.trim();
        
        Serial.print("Received command: ");
        Serial.println(command);
        
        if (command == "READ_EC") {
            auto ecData = ecSensor.processECSensor();
            Serial.print("EC Value: ");
            Serial.print(ecData.mS_cm, 2);
            Serial.println(" mS/cm");
        }
        // Direct test commands
        else if (command == "TEST_PIN_27") {
            Serial.println("TEST: Activating relay Y1 (pin 27) for 10 seconds");
            relayWrite(27, HIGH);
            delay(10000);
            relayWrite(27, LOW);
            Serial.println("TEST: Relay Y1 deactivated");
        }
        else if (command == "TEST_PIN_26") {
            Serial.println("TEST: Activating relay Y2 (pin 26) for 10 seconds");
            relayWrite(26, HIGH);
            delay(10000);
            relayWrite(26, LOW);
            Serial.println("TEST: Relay Y2 deactivated");
        }
        else if (command == "TEST_PIN_25") {
            Serial.println("TEST: Activating relay Y3 (pin 25) for 10 seconds");
            relayWrite(25, HIGH);
            delay(10000);
            relayWrite(25, LOW);
            Serial.println("TEST: Relay Y3 deactivated");
        }
        else if (command == "STATUS" || command == "{\"action\":\"status\"}") {
            Serial.println("{\"success\":true,\"status\":\"ready\",\"firmware\":\"ESP32 Hydro Controller V1\"}");
        }
        // Add this line to handle dosing commands
        else if (command.startsWith("{") && command.endsWith("}")) {
            handleDosingCommand(command);
        }
        else if (command == "RESET" || command == "INIT") {
            // Limpe todas as bombas (relays)
            relayWrite(25, LOW);
            relayWrite(26, LOW);
            relayWrite(27, LOW);
            
            // Limpe o buffer serial
            while (Serial.available() > 0) {
                Serial.read();
            }
            
            // Responda com confirmação
            Serial.println("{\"success\":true,\"status\":\"reset_complete\"}");
        }
    }
    
    // [5] Any final checks
    // ...
    // Comentado para evitar processamento redundante do EC
    // auto finalEcData = ecSensor.processECSensor();
    // float tdsValue = finalEcData.ppm;
}

// NEW: DS18B20 temperature reading function
float readDS18B20Temperature() {
  sensors.requestTemperatures();
  delay(750);  // Give sensor time to perform conversion
  float tempC = sensors.getTempCByIndex(0);
  if (tempC == DEVICE_DISCONNECTED_C) {
    tempC = -127.0; 
  }
  return tempC;
}

// Update your handleDosingCommand function
void handleDosingCommand(String command) {
    // Prepare o buffer para o documento JSON
    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, command);

    // Verifique se houve erro no parsing
    if (error) {
        Serial.print("JSON parsing failed: ");
        Serial.println(error.c_str());
        Serial.println("{\"success\":false,\"error\":\"json_parse_failed\"}");
        return;
    }

    // Extraia os campos necessários
    if (!doc.containsKey("action") || !doc.containsKey("pin") || !doc.containsKey("duration_ms")) {
        Serial.println("Error: Missing required fields in JSON");
        Serial.println("{\"success\":false,\"error\":\"missing_fields\"}");
        return;
    }

    String action = doc["action"];
    int pin = doc["pin"];
    int duration_ms = doc["duration_ms"];
    String pump_type = doc.containsKey("pump_type") ? doc["pump_type"].as<String>() : "unknown";

    // Valide os valores
    if (action != "dose") {
        Serial.println("Error: Invalid action. Must be 'dose'");
        Serial.println("{\"success\":false,\"error\":\"invalid_action\"}");
        return;
    }

    // Atualizar validação para incluir os novos PINs
    if (pin != 25 && pin != 26 && pin != 27 && pin != 23 && pin != 33 && pin != 19) {
        Serial.println("Error: Invalid pin number. Must be 25, 26, 27, 23, 33, or 19");
        Serial.println("{\"success\":false,\"error\":\"invalid_pin\"}");
        return;
    }

    if (duration_ms <= 0 || duration_ms > 60000) {
        Serial.println("Error: Invalid duration. Must be between 1 and 60000 ms");
        Serial.println("{\"success\":false,\"error\":\"invalid_duration\"}");
        return;
    }

    // Prepare a resposta JSON de início
    StaticJsonDocument<200> response;
    response["success"] = true;
    response["action"] = "dosing_start";
    response["pin"] = pin;
    response["duration_ms"] = duration_ms;
    response["pump_type"] = pump_type;

    // Serialize e envie a resposta
    serializeJson(response, Serial);
    Serial.println();

    // Ativar a bomba (relay)
    Serial.printf("Activating relay on pin %d for %d ms\n", pin, duration_ms);
    relayWrite(pin, HIGH);
    
    // Espere pelo tempo especificado
    delay(duration_ms);
    
    // Desativar a bomba (relay)
    relayWrite(pin, LOW);
    
    // Prepare a resposta JSON de conclusão
    response["action"] = "dosing_complete";
    
    // Serialize e envie a resposta
    serializeJson(response, Serial);
    Serial.println();
    
    Serial.println("Pump deactivated");
}
