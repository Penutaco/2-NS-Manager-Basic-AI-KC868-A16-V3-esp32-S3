#ifndef PHSENSOR_H
#define PHSENSOR_H

#include "Event.h"  // Ensure we can read ph_cal_points and ph_cal_count
#include <Adafruit_ADS1X15.h>  // Incluir biblioteca ADS1115

// Declarar objeto ADS1115 como externo
extern Adafruit_ADS1115 ads;

// Function prototypes
float processPHSensor(int pin);
float convertPHSensorVoltageToValue(float voltage);
float phMedianFilter(float newReading);
float phLowPassFilter(float newValue);

// First-stage: Moving Median Filter optimized for ESP32
float phMedianFilter(float newReading) {
  static const int windowSize = 60;  // Increased to 60 for 60-second window
  static float window[windowSize];
  static int index = 0;
  static bool windowFilled = false;
  
  // Store the new reading
  window[index] = newReading;
  index = (index + 1) % windowSize;
  
  if (index == 0) windowFilled = true;
  
  // Copy values to temporary array for sorting
  float sortedValues[windowSize];
  int actualSize = windowFilled ? windowSize : index;
  
  for (int i = 0; i < actualSize; i++) {
    sortedValues[i] = window[i];
  }
  
  // Simple bubble sort
  for (int i = 0; i < actualSize - 1; i++) {
    for (int j = 0; j < actualSize - i - 1; j++) {
      if (sortedValues[j] > sortedValues[j + 1]) {
        float temp = sortedValues[j];
        sortedValues[j] = sortedValues[j + 1];
        sortedValues[j + 1] = temp;
      }
    }
  }
  
  // Return the median value
  return sortedValues[actualSize / 2];
}

// Second-stage: Low-Pass IIR Filter with alpha optimized for 100s period
float phLowPassFilter(float newValue) {
  static float filteredValue = 0;
  static bool initialized = false;
  
  // Alpha optimized for 100s period noise
  const float alpha = 0.01;  // Smaller value for longer-period noise
  
  if (!initialized) {
    filteredValue = newValue;
    initialized = true;
    return newValue;
  }
  
  filteredValue = alpha * newValue + (1 - alpha) * filteredValue;
  return filteredValue;
}

float processPHSensor(int pin) {
  // Leitura via ADS1115 em vez de analogRead direto
  int16_t adc1 = ads.readADC_SingleEnded(1);  // A1 para o sensor de pH
  float voltage = ads.computeVolts(adc1);
  
  // Apply only the median filter
  float medianFiltered = phMedianFilter(voltage);
  
  // Skip the low-pass filter
  return medianFiltered;
}

// Updated conversion function for pH sensor voltage:
float convertPHSensorVoltageToValue(float voltage) {
    if (ph_cal_count < 2) {
        // Fallback to old fixed mapping
        return 4.0 + (voltage / 1.5) * 6.0;
    } else {
        float calLowVoltage = ph_cal_points[0];
        float calHighVoltage = ph_cal_points[1];
        float expectedLow = ph_cal_expected[0];
        float expectedHigh = ph_cal_expected[1];

        // Linear interpolation using measured voltages and expected pH values
        return expectedLow + ((voltage - calLowVoltage)
                    * (expectedHigh - expectedLow))
                    / (calHighVoltage - calLowVoltage);
    }
}

#endif // PHSENSOR_H