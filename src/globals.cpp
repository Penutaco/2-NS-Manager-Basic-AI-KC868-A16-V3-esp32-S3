#include "globals.h"
#include "Event.h"  // Add this so 'x' and 'y' are visible to main

// Comment out the duplicate EVENT_H block:
// #ifndef EVENT_H
// #define EVENT_H
// struct Event {
//     // ...existing code...
// };
// #endif // EVENT_H

#ifndef GLOBALS_H
#define GLOBALS_H

// Sensor values
extern float actualVoltage;
extern float refVoltage;
extern float Absorbancia;
extern bool CalibrationReady;
extern float ConcentracionCu;
extern float pRecta[2];

// Calibration points for the photoresistor
extern const int numCalibrationPoints;
extern float referenceVoltages[];
extern float concentrations[];

// Event control variables
extern bool isRef;        // Flag for Reference measurement
extern bool isMeasure;    // Flag for Sample measurement
extern float refValue;    // Store reference measurement
extern float measureValue; // Store sample measurement

#endif // GLOBALS_H

// Sensor values
float actualVoltage = 0.0;
float refVoltage = 0.0;
float Absorbancia = 0.0;
bool CalibrationReady = false;
float ConcentracionCu = 0.0;
float pRecta[2] = {0.0, 0.0};

// Calibration points for the photoresistor
const int numCalibrationPoints = 4;
float referenceVoltages[numCalibrationPoints] = {3.0, 2.5, 2.0, 1.5};  // Example reference voltages
float concentrations[numCalibrationPoints] = {0.0, 10.0, 20.0, 30.0};  // Corresponding concentrations

// Event control variables
bool isRef = false;
bool isMeasure = false;
float refValue = 0.0;
float measureValue = 0.0;

// Calibration data
float ph_cal_points[2] = {0.0, 0.0};
float nitrate_cal_points[2] = {0.0, 0.0};
int ph_cal_count = 0;  // Add this line
float ph_cal_expected[2] = {0.0, 0.0};  // Add this line

// PRGCal and PRGSample counters
int currentPRGCalCount = 0;  
int currentPRGSampleCount = 0;  

const int x = 1;  // PRGCal is performed once
const int y = 142;  // PRGSample is performed 286 times

// Adicionar junto às outras implementações de variáveis globais
float ecValue = 0.0;  // Global EC value in mS/cm
