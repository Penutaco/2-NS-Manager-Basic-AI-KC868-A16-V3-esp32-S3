#ifndef ECSENSOR_H
#define ECSENSOR_H

#include <Arduino.h>
#include <Adafruit_ADS1X15.h> // Include the Adafruit ADS1X15 library
#include "globals.h"  // Include globals.h for LED_PIN_21 and LED_PIN_22 definitions

#define VREF 3.3      // ESP32 ADC reference voltage
#define SCOUNT 60     // Number of sample points - increased to 60 for 60-second window
#define TEMP 25.0     // Fixed temperature for now, could be made variable

// Reference to the external ADS1115 object
extern Adafruit_ADS1115 ads;
// Reference to the current event
extern Event currentEvent;

class ECSensor {
private:
    int pin;
    int analogBuffer[SCOUNT];
    int analogBufferIndex = 0;
    float avgECmScm = 0;  // Changed from avgECppm
    float lastVoltage = 0;  // Store last voltage reading
    float lastMScm = 0;     // Changed from lastPPM
    
    // Median filtering function
    int getMedianNum(int bArray[], int iFilterLen) {
        int bTab[iFilterLen];
        for (byte i = 0; i < iFilterLen; i++)
            bTab[i] = bArray[i];
        
        // Bubble sort
        for (int j = 0; j < iFilterLen - 1; j++) {
            for (int i = 0; i < iFilterLen - j - 1; i++) {
                if (bTab[i] > bTab[i + 1]) {
                    int temp = bTab[i];
                    bTab[i] = bTab[i + 1];
                    bTab[i + 1] = temp;
                }
            }
        }
        
        // Return median value
        if ((iFilterLen & 1) > 0)
            return bTab[(iFilterLen - 1) / 2];
        else
            return (bTab[iFilterLen / 2] + bTab[iFilterLen / 2 - 1]) / 2;
    }

public:
    ECSensor(int sensorPin) : pin(sensorPin) {}

    // Updated struct to use mS/cm instead of PPM
    struct ECReadings {
        float voltage;
        float mS_cm;  // Changed from ppm to mS_cm
    };

    ECReadings processECSensor() {
        // Reading via ADS1115 instead of direct analogRead
        int16_t adc0 = ads.readADC_SingleEnded(0);  // A0 for EC sensor
        float averageVoltage = ads.computeVolts(adc0);
        
        // Temperature compensation remains the same
        float compensationCoefficient = 1.0 + 0.02 * (TEMP - 25.0);
        float compensationVoltage = averageVoltage / compensationCoefficient;

        // Linear calibration formula (Calibration curve of a D1/2 dilution)
        float mScmValue = 0.885 * compensationVoltage + 0.2925;

        lastVoltage = averageVoltage;
        lastMScm = mScmValue;  // Changed from lastPPM

        return {averageVoltage, mScmValue};  // Return mS/cm instead of PPM
    }
};

#endif // ECSENSOR_H