#ifndef PHOTORESISTOR_H
#define PHOTORESISTOR_H

#include <Arduino.h>
#include <Adafruit_ADS1X15.h>
#include "globals.h"

// Declarar objeto ADS1115 como externo
extern Adafruit_ADS1115 ads;

float processPhotoresistor(int pin) {
    int16_t adc2 = ads.readADC_SingleEnded(2);  // A2 para o fotorresistor
    float voltage = ads.computeVolts(adc2);
    return voltage;
}

float calculateAbsorbance(float sampleVoltage, float referenceVoltage) {
    if (referenceVoltage <= 0) {
        return 0.0;  // Avoid division by zero
    }
    return log10(referenceVoltage / sampleVoltage);
}

#endif // PHOTORESISTOR_H