#ifndef NITRATESENSOR_H
#define NITRATESENSOR_H

#include <Arduino.h>
#include <Adafruit_ADS1X15.h>  // Adicionar para o ADS1115
#include "globals.h"

// Declarar objeto ADS1115 como externo
extern Adafruit_ADS1115 ads;

float nitrateMedianFilter(float newReading) {
  static const int windowSize = 60;  // 60-sample window for 60-second filtering
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

float processNitrateSensor(int pin) {
    int16_t adc3 = ads.readADC_SingleEnded(3);  // A3 para o sensor de nitrato
    float voltage = ads.computeVolts(adc3);
    return nitrateMedianFilter(voltage * 100.0);  // Apply median filter
}

#endif // NITRATESENSOR_H