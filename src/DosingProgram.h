// DosingProgram.h - 14-Stage Programmable Dosing System
#ifndef DOSINGPROGRAM_H
#define DOSINGPROGRAM_H

#include "Event.h"
#include <Arduino.h>

// Pump pin definitions
#define PH_PLUS_PIN 27
#define PH_MINUS_PIN 26
#define EC_PLUS_SOLA_PIN 25
#define EC_PLUS_SOLB_PIN 23
#define EC_PLUS_SOLC_PIN 33
#define EC_MINUS_H2O_PIN 19

// Dosing stage configuration structure
struct DosingStage {
    int stage_number;           // Stage 1-14
    float target_ph;            // Target pH for this stage
    float target_ec;            // Target EC (mS/cm) for this stage
    float ph_tolerance;         // pH tolerance (±)
    float ec_tolerance;         // EC tolerance (±)
    unsigned long duration_hours; // Stage duration in hours
    bool ec_continuous_monitoring; // Continuous EC monitoring flag
    float ratio_sol_a;          // Solution A ratio (0.0-1.0)
    float ratio_sol_b;          // Solution B ratio (0.0-1.0)  
    float ratio_sol_c;          // Solution C ratio (0.0-1.0)
    unsigned long cooldown_minutes; // Cooldown between dosing (minutes)
    float dosing_safety_factor; // Safety factor for dosing volume (0.5-1.0)
    bool enabled;               // Stage enabled/disabled
};

// Define the number of dosing stages
const int numDosingStages = 14;

// External declaration of the dosing program array (defined in DosingProgram.cpp)
extern DosingStage dosingProgram[numDosingStages];

// Dosing system state tracking
struct DosingSystemState {
    float tank_volume_liters; // Total tank volume in liters
    int current_stage;
    unsigned long stage_start_time;
    unsigned long program_start_time;
    unsigned long last_dosing_time;
    int cycles_since_dosing;
    bool dosing_enabled;
    int total_dosing_actions;
    
    // Chemistry-based coefficient tracking (matching Python implementation)
    float ph_plus_molarity;          // Molarity of pH+ solution (e.g., 0.1M KOH)
    float ph_minus_molarity;         // Molarity of pH- solution (e.g., 0.1M HCl)
    float pump_flow_rate_ml_min;     // Pump flow rate in ml/min
    float ec_up_volume_per_ec;       // mL of EC+ solution per L per 1.0 mS/cm increase
    float h2o_dilution_coefficient;  // mL of H2O per L per 1.0 mS/cm decrease
    
    // Adaptive learning coefficients (calculated from chemistry + experience)
    float ph_plus_coefficient;       // pH units per mL (derived from molarity)
    float ph_minus_coefficient;      // pH units per mL (derived from molarity)
    float ec_conductivity_coefficient; // EC change per mL (derived from chemistry)
    
    // History tracking
    float ph_history[10];
    float ec_history[10];
    int history_index;
    
    // Learning system tracking (cycle-to-cycle learning)
    bool learning_enabled;             // Enable/disable adaptive learning
    int last_cycle_id;                 // Track last processed cycle for learning
    String last_cycle_pump_type;       // What was dosed in previous cycle
    float last_cycle_volume_dosed;     // Volume dosed in previous cycle
    float last_cycle_expected_change;  // Expected change from previous cycle
    float last_cycle_ph;               // pH from previous cycle (before dosing)
    float last_cycle_ec;               // EC from previous cycle (before dosing)
    bool has_previous_cycle_data;      // Flag indicating we have data to learn from
    
    // Error tracking
    int error_count;
    bool system_healthy;
};

// Function declarations
void initDosingSystem();
void initChemistryBasedCoefficients();  // NEW: Initialize coefficients based on chemistry
void updateDosingStage();
DosingStage getCurrentStage();
bool checkAndDose(int cycle_id, float current_ph, float current_ec);
void dosePump(int pin, int duration_ms, String pump_type, float volume_ml);
void updateCoefficients(String pump_type, float expected_change, float observed_change);
void recordCycleForLearning(int cycle_id, String pump_type, float volume_dosed, float expected_change, float current_ph, float current_ec);
void applyLearningFromPreviousCycle(int current_cycle_id, float current_ph, float current_ec);
void logDosingAction(String pump_type, int pin, int duration_ms, float volume_ml);
float calculateDosingVolume(float current_value, float target_value, float coefficient);  // Legacy function - deprecated
float calculatePhDosingVolume(float current_ph, float target_ph, float ph_coefficient);
float calculateEcDosingVolume(float current_ec, float target_ec, float ec_coefficient);
int volumeToDosingTime(float volume_ml, float flow_rate_ml_min = 50.0);
void addToHistory(float ph_value, float ec_value);
float getAverageFromHistory(float history[], int size);
bool isDoseAllowed();

// Global dosing system state
extern DosingSystemState dosing_system;

// Default tank volume (liters)
extern float tank_volume_liters;

#endif // DOSINGPROGRAM_H
