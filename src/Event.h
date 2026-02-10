#ifndef EVENT_H
#define EVENT_H

struct Event {
    unsigned long waitTime;
    bool refValue;
    bool measureValue;
    int ledState;
    float expectedPH;       // Expected pH value for calibration
    float expectedNitrate;  // Expected Nitrate value for calibration
    float expectedEC;       // Expected EC value for calibration - ADD THIS LINE
};

// Declare the constants as external
extern const int numPRGcalEvents;
extern const int numPRGsampleEvents;

// Declare the event arrays
extern Event PRGcalEvents[];
extern Event PRGsampleEvents[];

// Declare the counts for cycles as external
extern const int x;   // Number of PRGcal cycles
extern const int y;   // Number of PRGsample cycles

// Original definitions (commented out to avoid multiple definitions):
// float ph_cal_points[2] = {0.0, 0.0};
// int ph_cal_count = 0;
// float ph_cal_expected[2] = {0.0, 0.0};
// float nitrate_cal_points[2] = {0.0, 0.0};
// int nitrate_cal_count = 0;

// Convert them to extern declarations
extern float ph_cal_points[2];
extern int ph_cal_count;
extern float ph_cal_expected[2];
extern float nitrate_cal_points[2];
extern int nitrate_cal_count;

// Function declaration for processing PRG calibration
void processPRGCalibration(unsigned long currentMillis);

#endif // EVENT_H
