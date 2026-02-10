// DosingProgram.cpp - Implementation of 14-Stage Programmable Dosing System
// 
// TYPE-SAFE DOSING CALCULATIONS:
// - calculatePhDosingVolume(): Type-safe pH dosing using pH units per mL coefficients
// - calculateEcDosingVolume(): Type-safe EC dosing using mL/L/mS/cm coefficients  
// - calculateDosingVolume(): DEPRECATED legacy function (kept for compatibility)
//
// CHEMICAL FORMULAS (matching Python implementation):
// - pH: volume_ml = ph_difference / ph_coefficient
// - EC: volume_ml = ec_difference * ec_coefficient * tank_volume_liters
//
#include <Arduino.h>
#include "DosingProgram.h"
#include "globals.h"
#include "relay_wrapper.h"  // V3 Migration: Required for relayWrite() I2C control

// Define the 14-stage dosing program based on your Python configuration
DosingStage dosingProgram[numDosingStages] = {
    // Stage 1: Initial Growth Phase
    {1, 6.0, 1.5, 0.2, 0.1, 720, true, 1.0, 1.0, 0.0, 5, 1.0, true},

    // Stage 2: Early Vegetative
    {2, 5.8, 1.8, 0.2, 0.1, 72, false, 1.0, 1.0, 0.0, 5, 1.0, true},

    // Stage 3: Mid Vegetative
    {3, 5.8, 2.0, 0.2, 0.1, 96, false, 1.0, 1.0, 0.5, 5, 1.0, true},
    
    // Stage 4: Late Vegetative
    {4, 6.0, 2.2, 0.2, 0.1, 72, false, 0.8, 1.0, 0.8, 5, 1.0, true},
    
    // Stage 5: Pre-Flowering Transition
    {5, 6.1, 2.0, 0.2, 0.1, 48, false, 0.6, 1.0, 1.0, 5, 1.0, true},
    
    // Stage 6: Early Flowering
    {6, 6.2, 1.8, 0.2, 0.1, 96, false, 0.4, 0.8, 1.0, 5, 0.8, true},
    
    // Stage 7: Mid Flowering
    {7, 6.2, 1.6, 0.2, 0.1, 120, false, 0.2, 0.6, 1.0, 5, 0.8, true},
    
    // Stage 8: Late Flowering
    {8, 6.3, 1.4, 0.2, 0.1, 96, false, 0.1, 0.4, 1.0, 5, 0.8, true},
    
    // Stage 9: Pre-Harvest Flush
    {9, 6.5, 0.8, 0.3, 0.2, 72, false, 0.0, 0.0, 0.0, 10, 0.5, true},
    
    // Stage 10: Final Flush
    {10, 6.5, 0.4, 0.3, 0.2, 48, false, 0.0, 0.0, 0.0, 15, 0.5, true},
    
    // Stage 11: Harvest Preparation
    {11, 6.8, 0.2, 0.4, 0.3, 24, false, 0.0, 0.0, 0.0, 30, 0.3, true},
    
    // Stage 12: Post-Harvest Clean
    {12, 7.0, 0.1, 0.5, 0.5, 12, false, 0.0, 0.0, 0.0, 60, 0.3, false},
    
    // Stage 13: System Maintenance
    {13, 7.0, 0.0, 1.0, 1.0, 6, false, 0.0, 0.0, 0.0, 120, 0.1, false},
    
    // Stage 14: Reset/Standby
    {14, 6.0, 1.0, 0.5, 0.5, 24, false, 0.5, 0.5, 0.0, 30, 1.0, false}
};

// Global dosing system state
DosingSystemState dosing_system;

void initDosingSystem() {
    // Initialize dosing system state
    dosing_system.current_stage = 1;
    dosing_system.stage_start_time = millis();
    dosing_system.program_start_time = millis();
    dosing_system.last_dosing_time = 0;
    dosing_system.cycles_since_dosing = 0;
    dosing_system.dosing_enabled = true;
    dosing_system.total_dosing_actions = 0;
    
    // Initialize chemistry-based coefficients (matching Python implementation)
    initChemistryBasedCoefficients();
    
    // Initialize history arrays
    dosing_system.history_index = 0;
    for (int i = 0; i < 10; i++) {
        dosing_system.ph_history[i] = 0.0;
        dosing_system.ec_history[i] = 0.0;
    }
    
    // Initialize learning system (cycle-to-cycle learning)
    dosing_system.learning_enabled = true;
    dosing_system.last_cycle_id = -1;  // No previous cycle initially
    dosing_system.last_cycle_pump_type = "";
    dosing_system.last_cycle_volume_dosed = 0.0;
    dosing_system.last_cycle_expected_change = 0.0;
    dosing_system.last_cycle_ph = 0.0;
    dosing_system.last_cycle_ec = 0.0;
    dosing_system.has_previous_cycle_data = false;
    
    // Initialize error tracking
    dosing_system.error_count = 0;
    dosing_system.system_healthy = true;
    
    Serial.println("=== Dosing System Initialized ===");
    Serial.printf("Starting at Stage %d\n", dosing_system.current_stage);
    DosingStage current = getCurrentStage();
    Serial.printf("Target: pH=%.1f, EC=%.1f mS/cm\n", current.target_ph, current.target_ec);
    Serial.printf("Tolerances: pH±%.1f, EC±%.1f\n", current.ph_tolerance, current.ec_tolerance);
}

void updateDosingStage() {
    DosingStage current = getCurrentStage();
    unsigned long elapsed_hours = (millis() - dosing_system.stage_start_time) / (1000UL * 60UL * 60UL);
    
    // Check if current stage duration has elapsed
    if (elapsed_hours >= current.duration_hours && dosing_system.current_stage < numDosingStages) {
        dosing_system.current_stage++;
        dosing_system.stage_start_time = millis();
        
        DosingStage new_stage = getCurrentStage();
        Serial.println("=== STAGE TRANSITION ===");
        Serial.printf("Advanced to Stage %d\n", dosing_system.current_stage);
        Serial.printf("New Target: pH=%.1f, EC=%.1f mS/cm\n", new_stage.target_ph, new_stage.target_ec);
        Serial.printf("Duration: %lu hours\n", new_stage.duration_hours);
        
        // Log stage transition in enhanced format
        Serial.printf("STAGE_TRANSITION,%lu,%d,%d,%.1f,%.1f,%.1f,%.1f,%lu\n",
            millis(), dosing_system.current_stage - 1, dosing_system.current_stage,
            current.target_ph, new_stage.target_ph, current.target_ec, new_stage.target_ec,
            new_stage.duration_hours);
    }
}

DosingStage getCurrentStage() {
    if (dosing_system.current_stage > 0 && dosing_system.current_stage <= numDosingStages) {
        return dosingProgram[dosing_system.current_stage - 1];
    }
    // Return stage 1 as default
    return dosingProgram[0];
}

bool checkAndDose(int cycle_id, float current_ph, float current_ec) {
    Serial.printf("=== DOSING CHECK START (Cycle %d) ===\n", cycle_id);
    Serial.printf("Current: pH=%.2f, EC=%.2f\n", current_ph, current_ec);
    
    // Apply learning from previous cycle FIRST (like Python system)
    if (dosing_system.learning_enabled) {
        applyLearningFromPreviousCycle(cycle_id, current_ph, current_ec);
    }
    
    if (!dosing_system.dosing_enabled) {
        Serial.println("BLOCK: Dosing system disabled");
        return false;
    }
    
    updateDosingStage();
    DosingStage stage = getCurrentStage();
    
    Serial.printf("Stage %d: Target pH=%.1f±%.1f, EC=%.1f±%.1f\n", 
        stage.stage_number, stage.target_ph, stage.ph_tolerance, stage.target_ec, stage.ec_tolerance);
    
    if (!stage.enabled) {
        Serial.printf("BLOCK: Stage %d is disabled\n", stage.stage_number);
        return false;
    }
    
    // Check cooldown
    if (!isDoseAllowed()) {
        Serial.println("BLOCK: Cooldown period active");
        return false;
    }
    
    // Add to history
    addToHistory(current_ph, current_ec);
    
    // Calculate deviations
    float ph_diff = stage.target_ph - current_ph;
    float ec_diff = stage.target_ec - current_ec;
    
    Serial.printf("Deviations: pH diff=%.2f (need >%.1f), EC diff=%.2f (need >%.1f)\n", 
        abs(ph_diff), stage.ph_tolerance, abs(ec_diff), stage.ec_tolerance);
    
    bool dosing_needed = false;
    
    // pH Dosing Logic
    if (abs(ph_diff) > stage.ph_tolerance) {
        dosing_needed = true;
        
        if (ph_diff > 0) {
            // Need to increase pH
            float volume_needed = calculatePhDosingVolume(current_ph, stage.target_ph, dosing_system.ph_plus_coefficient);
            volume_needed *= stage.dosing_safety_factor;
            int dosing_time = volumeToDosingTime(volume_needed);
            
            Serial.printf("pH Dosing Decision: %.2f → %.1f (diff: %.2f), Volume: %.2f mL, Time: %d ms\n",
                current_ph, stage.target_ph, ph_diff, volume_needed, dosing_time);
            
            // Record this cycle for next cycle's learning
            recordCycleForLearning(cycle_id, "ph_plus", volume_needed, abs(ph_diff), current_ph, current_ec);
            
            dosePump(PH_PLUS_PIN, dosing_time, "ph_plus", volume_needed);
            
        } else {
            // Need to decrease pH
            float volume_needed = calculatePhDosingVolume(current_ph, stage.target_ph, dosing_system.ph_minus_coefficient);
            volume_needed *= stage.dosing_safety_factor;
            int dosing_time = volumeToDosingTime(volume_needed);
            
            Serial.printf("pH Dosing Decision: %.2f → %.1f (diff: %.2f), Volume: %.2f mL, Time: %d ms\n",
                current_ph, stage.target_ph, ph_diff, volume_needed, dosing_time);
            
            // Record this cycle for next cycle's learning
            recordCycleForLearning(cycle_id, "ph_minus", volume_needed, abs(ph_diff), current_ph, current_ec);
            
            dosePump(PH_MINUS_PIN, dosing_time, "ph_minus", volume_needed);
        }
    }
    
    // EC Dosing Logic (only if EC monitoring is enabled)
    if (stage.ec_continuous_monitoring && abs(ec_diff) > stage.ec_tolerance) {
        dosing_needed = true;
        
        if (ec_diff > 0) {
            // Need to increase EC - Multi-pump strategy
            float total_volume = calculateEcDosingVolume(current_ec, stage.target_ec, dosing_system.ec_conductivity_coefficient);
            total_volume *= stage.dosing_safety_factor;
            
            // Distribute volume according to solution ratios
            float vol_a = total_volume * stage.ratio_sol_a;
            float vol_b = total_volume * stage.ratio_sol_b;
            float vol_c = total_volume * stage.ratio_sol_c;
            
            Serial.printf("EC Dosing Decision: %.2f → %.1f (diff: %.2f), Total: %.2f mL\n",
                current_ec, stage.target_ec, ec_diff, total_volume);
            Serial.printf("Solution Distribution: A=%.2f, B=%.2f, C=%.2f mL\n", vol_a, vol_b, vol_c);
            
            // Record this cycle for next cycle's learning (track total EC volume)
            recordCycleForLearning(cycle_id, "ec_sol_total", total_volume, abs(ec_diff), current_ph, current_ec);
            
            if (vol_a > 0) dosePump(EC_PLUS_SOLA_PIN, volumeToDosingTime(vol_a), "ec_sol_a", vol_a);
            if (vol_b > 0) dosePump(EC_PLUS_SOLB_PIN, volumeToDosingTime(vol_b), "ec_sol_b", vol_b);
            if (vol_c > 0) dosePump(EC_PLUS_SOLC_PIN, volumeToDosingTime(vol_c), "ec_sol_c", vol_c);
            
        } else {
            // Need to decrease EC - Add water
            float volume_needed = calculateEcDosingVolume(current_ec, stage.target_ec, dosing_system.h2o_dilution_coefficient);
            volume_needed *= stage.dosing_safety_factor;
            int dosing_time = volumeToDosingTime(volume_needed);
            
            Serial.printf("H2O Dosing Decision: %.2f → %.1f (diff: %.2f), Volume: %.2f mL, Time: %d ms\n",
                current_ec, stage.target_ec, ec_diff, volume_needed, dosing_time);
            
            // Record this cycle for next cycle's learning
            recordCycleForLearning(cycle_id, "h2o", volume_needed, abs(ec_diff), current_ph, current_ec);
            
            dosePump(EC_MINUS_H2O_PIN, dosing_time, "h2o", volume_needed);
        }
    }
    
    if (dosing_needed) {
        dosing_system.last_dosing_time = millis();
        dosing_system.cycles_since_dosing = 0;
        dosing_system.total_dosing_actions++;
        
        Serial.printf("✅ DOSING COMPLETED: Action #%d at %lu ms\n", 
            dosing_system.total_dosing_actions, dosing_system.last_dosing_time);
        
        // Enhanced format status update
        Serial.printf("DOSING_STATUS,%lu,%d,%d,%s,%s,%lu,%d,%d\n",
            millis(), dosing_system.current_stage, dosing_system.total_dosing_actions,
            abs(ph_diff) <= stage.ph_tolerance ? "true" : "false",
            abs(ec_diff) <= stage.ec_tolerance ? "true" : "false",
            dosing_system.last_dosing_time, dosing_system.cycles_since_dosing,
            dosing_system.system_healthy ? 100 : 50);
    } else {
        dosing_system.cycles_since_dosing++;
        Serial.printf("❌ NO DOSING: pH: %.2f (±%.1f), EC: %.2f (±%.1f)\n",
            current_ph, stage.ph_tolerance, current_ec, stage.ec_tolerance);
    }
    
    Serial.printf("=== DOSING CHECK END ===\n");
    return dosing_needed;
}

void dosePump(int pin, int duration_ms, String pump_type, float volume_ml) {
    // V3 Migration: Removed pinMode - I2C relays don't need GPIO configuration
    
    // Log dosing action in enhanced format
    logDosingAction(pump_type, pin, duration_ms, volume_ml);
    
    // Activate pump via I2C relay wrapper
    relayWrite(pin, HIGH);
    Serial.printf("PUMP_ON,%lu,%s,%d,%d,%.2f\n", millis(), pump_type.c_str(), pin, duration_ms, volume_ml);
    
    // Wait for dosing duration
    delay(duration_ms);
    
    // Deactivate pump via I2C relay wrapper
    relayWrite(pin, LOW);
    Serial.printf("PUMP_OFF,%lu,%s,%d\n", millis(), pump_type.c_str(), pin);
    
    Serial.printf("Dosing completed: %s on pin %d for %d ms (%.2f mL)\n", 
        pump_type.c_str(), pin, duration_ms, volume_ml);
}

// Chemistry-based coefficient initialization (matching Python implementation)
void initChemistryBasedCoefficients() {
    // Initialize chemistry parameters (matching Python CONFIG values)
    dosing_system.ph_minus_molarity = 0.1;      // 0.1M HCl
    dosing_system.ph_plus_molarity = 0.1;       // 0.1M KOH  
    dosing_system.pump_flow_rate_ml_min = 50.0; // 50 ml/min
    dosing_system.ec_up_volume_per_ec = 2.5;    // mL per L per 1.0 mS/cm increase
    dosing_system.h2o_dilution_coefficient = 1.0; // mL per L per 1.0 mS/cm decrease
    dosing_system.tank_volume_liters = 15.0;    // 15L tank volume
    
    // CORRECTED: Use Python's exact formula - coefficients are directly the molarity values
    // Python: self.ph_plus_titration_coefficient = self.config.get('ph_plus_molarity', 0.1)
    dosing_system.ph_plus_coefficient = dosing_system.ph_plus_molarity;    // 0.1 pH units per mL (NOT * 0.1)
    dosing_system.ph_minus_coefficient = dosing_system.ph_minus_molarity;  // 0.1 pH units per mL (NOT * 0.1)
    
    // CORRECTED: EC coefficient should NOT be divided by tank volume here
    // Python: self.ec_specific_conductivity_coefficient = self.config.get('ec_up_volume_per_ec', 2.5)
    // Tank volume is applied during volume calculation, not coefficient initialization
    dosing_system.ec_conductivity_coefficient = dosing_system.ec_up_volume_per_ec;  // 2.5 mL/L/mS/cm (NOT divided by tank volume)
    
    // Log chemistry-based initialization with corrected formulas
    Serial.printf("CHEMISTRY_INIT,%lu,ph_plus_molarity,%.2f,ph_minus_molarity,%.2f\n",
        millis(), dosing_system.ph_plus_molarity, dosing_system.ph_minus_molarity);
    Serial.printf("CHEMISTRY_INIT,%lu,pump_flow_rate,%.1f,tank_volume,%.1f\n",
        millis(), dosing_system.pump_flow_rate_ml_min, dosing_system.tank_volume_liters);
    Serial.printf("CHEMISTRY_INIT,%lu,ec_up_vol_per_ec,%.2f,h2o_dilution,%.2f\n", 
        millis(), dosing_system.ec_up_volume_per_ec, dosing_system.h2o_dilution_coefficient);
    Serial.printf("COEFFICIENT_INIT_CORRECTED,%lu,ph_plus,%.3f,ph_minus,%.3f,ec_conductivity,%.3f\n",
        millis(), dosing_system.ph_plus_coefficient, dosing_system.ph_minus_coefficient, 
        dosing_system.ec_conductivity_coefficient);
    Serial.printf("FORMULA_INFO,%lu,pH_formula,volume=effect/coefficient,EC_formula,volume=effect*coefficient*tank_volume\n", millis());
}

float calculateDosingVolume(float current_value, float target_value, float coefficient) {
    // DEPRECATED: Use calculatePhDosingVolume() or calculateEcDosingVolume() for type safety
    Serial.printf("DEPRECATED_FUNCTION_WARNING,%lu,calculateDosingVolume,use_type_safe_alternatives\n", millis());
    
    float effect = abs(target_value - current_value);
    float volume_ml;
    
    // LEGACY: Keep original threshold-based logic for backward compatibility
    
    if (coefficient >= 2.0) {
        // This is an EC coefficient (≥2.0 indicates mL/L/mS/cm units)
        // Python formula: ml_needed = ec_difference * self.ec_specific_conductivity_coefficient * self.config['tank_volume_liters']
        volume_ml = effect * coefficient * dosing_system.tank_volume_liters;
        Serial.printf("DOSE_CALC_EC_LEGACY,%lu,effect,%.3f,coefficient,%.3f,tank_vol,%.1f,volume,%.2f\n",
            millis(), effect, coefficient, dosing_system.tank_volume_liters, volume_ml);
    } else {
        // This is a pH coefficient (pH units per mL)
        // Python formula: ml_needed = ph_difference / self.ph_plus_titration_coefficient
        volume_ml = effect / coefficient;
        Serial.printf("DOSE_CALC_PH_LEGACY,%lu,effect,%.3f,coefficient,%.3f,volume,%.2f\n",
            millis(), effect, coefficient, volume_ml);
    }
    
    // Minimum and maximum volume constraints
    const float MIN_VOLUME = 0.1;  // 0.1 mL minimum
    const float MAX_VOLUME = 10.0; // 10 mL maximum per dose
    if (volume_ml < MIN_VOLUME) volume_ml = MIN_VOLUME;
    if (volume_ml > MAX_VOLUME) volume_ml = MAX_VOLUME;
    
    return volume_ml;
}

// NEW: Type-safe pH dosing volume calculation
float calculatePhDosingVolume(float current_ph, float target_ph, float ph_coefficient) {
    float ph_effect = abs(target_ph - current_ph);
    
    // pH formula: ml_needed = ph_difference / ph_titration_coefficient
    // Where ph_coefficient is in pH units per mL
    float volume_ml = ph_effect / ph_coefficient;
    
    Serial.printf("PH_DOSE_CALC,%lu,current_ph,%.2f,target_ph,%.2f,effect,%.3f,coefficient,%.3f,volume,%.2f\n",
        millis(), current_ph, target_ph, ph_effect, ph_coefficient, volume_ml);
    
    // Apply volume constraints
    const float MIN_VOLUME = 0.1;  // 0.1 mL minimum
    const float MAX_VOLUME = 10.0; // 10 mL maximum per dose
    if (volume_ml < MIN_VOLUME) volume_ml = MIN_VOLUME;
    if (volume_ml > MAX_VOLUME) volume_ml = MAX_VOLUME;
    
    return volume_ml;
}

// NEW: Type-safe EC dosing volume calculation
float calculateEcDosingVolume(float current_ec, float target_ec, float ec_coefficient) {
    float ec_effect = abs(target_ec - current_ec);
    
    // EC formula: ml_needed = ec_difference * ec_coefficient * tank_volume_liters
    // Where ec_coefficient is in mL/L/mS/cm units
    float volume_ml = ec_effect * ec_coefficient * dosing_system.tank_volume_liters;
    
    Serial.printf("EC_DOSE_CALC,%lu,current_ec,%.2f,target_ec,%.2f,effect,%.3f,coefficient,%.3f,tank_vol,%.1f,volume,%.2f\n",
        millis(), current_ec, target_ec, ec_effect, ec_coefficient, dosing_system.tank_volume_liters, volume_ml);
    
    // Apply volume constraints
    const float MIN_VOLUME = 0.1;  // 0.1 mL minimum
    const float MAX_VOLUME = 10.0; // 10 mL maximum per dose
    if (volume_ml < MIN_VOLUME) volume_ml = MIN_VOLUME;
    if (volume_ml > MAX_VOLUME) volume_ml = MAX_VOLUME;
    
    return volume_ml;
}

int volumeToDosingTime(float volume_ml, float flow_rate_ml_min) {
    // Use system flow rate if not provided (matching Python implementation)
    if (flow_rate_ml_min <= 0) {
        flow_rate_ml_min = dosing_system.pump_flow_rate_ml_min;
    }
    
    // Convert volume to milliseconds based on flow rate
    int dosing_time_ms = (volume_ml / flow_rate_ml_min) * 60000; // Convert min to ms
    
    Serial.printf("VOLUME_TO_TIME,%lu,volume,%.2f,flow_rate,%.1f,time_ms,%d\n",
        millis(), volume_ml, flow_rate_ml_min, dosing_time_ms);
    
    // Minimum and maximum time constraints
    const int MIN_TIME = 100;   // 100ms minimum
    const int MAX_TIME = 60000; // 60 seconds maximum
    
    if (dosing_time_ms < MIN_TIME) dosing_time_ms = MIN_TIME;
    if (dosing_time_ms > MAX_TIME) dosing_time_ms = MAX_TIME;
    
    return dosing_time_ms;
}

void addToHistory(float ph_value, float ec_value) {
    dosing_system.ph_history[dosing_system.history_index] = ph_value;
    dosing_system.ec_history[dosing_system.history_index] = ec_value;
    dosing_system.history_index = (dosing_system.history_index + 1) % 10;
}

float getAverageFromHistory(float history[], int size) {
    float sum = 0.0;
    int count = 0;
    for (int i = 0; i < size; i++) {
        if (history[i] > 0) {
            sum += history[i];
            count++;
        }
    }
    return count > 0 ? sum / count : 0.0;
}

bool isDoseAllowed() {
    DosingStage stage = getCurrentStage();
    unsigned long cooldown_ms = stage.cooldown_minutes * 60000UL;
    
    if (millis() - dosing_system.last_dosing_time < cooldown_ms) {
        unsigned long remaining = cooldown_ms - (millis() - dosing_system.last_dosing_time);
        Serial.printf("Dosing cooldown active: %lu ms remaining\n", remaining);
        return false;
    }
    
    return true;
}

void logDosingAction(String pump_type, int pin, int duration_ms, float volume_ml) {
    // Enhanced format dosing action log
    Serial.printf("DOSING_ACTION,%lu,%d,%s,%d,%d,%.2f,50.0,%lu,%lu,EXECUTING,20000,single\n",
        millis(), dosing_system.current_stage, pump_type.c_str(), pin, duration_ms, volume_ml,
        millis(), millis() + duration_ms);
}

void updateCoefficients(String pump_type, float expected_change, float observed_change) {
    const float LEARNING_RATE = 0.2;
    
    // Log coefficient update attempt
    Serial.printf("COEFFICIENT_UPDATE_ATTEMPT,%lu,%s,%.3f,%.3f,%.2f\n",
        millis(), pump_type.c_str(), expected_change, observed_change, LEARNING_RATE);
    
    if (abs(observed_change) < 0.01) {
        // FIXED: If no measurable effect, HALVE the coefficient (not double!)
        // This will result in MORE volume being dosed next time (volume = effect / coefficient)
        Serial.printf("COEFFICIENT_NO_EFFECT,%lu,%s,halving_coefficient\n", millis(), pump_type.c_str());
        
        if (pump_type == "ph_plus") {
            float old_coeff = dosing_system.ph_plus_coefficient;
            dosing_system.ph_plus_coefficient = constrain(dosing_system.ph_plus_coefficient / 2.0, 0.01, 0.5);
            Serial.printf("COEFFICIENT_UPDATE,%lu,%s,%.4f,%.4f,no_effect,halved\n",
                millis(), pump_type.c_str(), old_coeff, dosing_system.ph_plus_coefficient);
        } else if (pump_type == "ph_minus") {
            float old_coeff = dosing_system.ph_minus_coefficient;
            dosing_system.ph_minus_coefficient = constrain(dosing_system.ph_minus_coefficient / 2.0, 0.01, 0.5);
            Serial.printf("COEFFICIENT_UPDATE,%lu,%s,%.4f,%.4f,no_effect,halved\n",
                millis(), pump_type.c_str(), old_coeff, dosing_system.ph_minus_coefficient);
        } else if (pump_type.startsWith("ec_sol")) {
            float old_coeff = dosing_system.ec_conductivity_coefficient;
            dosing_system.ec_conductivity_coefficient = constrain(dosing_system.ec_conductivity_coefficient / 2.0, 0.5, 10.0);
            Serial.printf("COEFFICIENT_UPDATE,%lu,%s,%.4f,%.4f,no_effect,halved\n",
                millis(), pump_type.c_str(), old_coeff, dosing_system.ec_conductivity_coefficient);
        } else if (pump_type == "h2o") {
            float old_coeff = dosing_system.h2o_dilution_coefficient;
            dosing_system.h2o_dilution_coefficient = constrain(dosing_system.h2o_dilution_coefficient / 2.0, 0.1, 5.0);
            Serial.printf("COEFFICIENT_UPDATE,%lu,%s,%.4f,%.4f,no_effect,halved\n",
                millis(), pump_type.c_str(), old_coeff, dosing_system.h2o_dilution_coefficient);
        }
        return;
    }
    
    // Normal adaptive learning with observed effect
    float ratio = observed_change / expected_change;
    
    if (pump_type == "ph_plus") {
        float old = dosing_system.ph_plus_coefficient;
        float new_coeff = old + LEARNING_RATE * (old * ratio - old);
        dosing_system.ph_plus_coefficient = constrain(new_coeff, 0.01, 0.5);
        Serial.printf("COEFFICIENT_UPDATE,%lu,%s,%.4f,%.4f,%.3f,%.3f,%.2f,adaptive\n",
            millis(), pump_type.c_str(), old, dosing_system.ph_plus_coefficient, 
            expected_change, observed_change, LEARNING_RATE);
    } else if (pump_type == "ph_minus") {
        float old = dosing_system.ph_minus_coefficient;
        float new_coeff = old + LEARNING_RATE * (old * ratio - old);
        dosing_system.ph_minus_coefficient = constrain(new_coeff, 0.01, 0.5);
        Serial.printf("COEFFICIENT_UPDATE,%lu,%s,%.4f,%.4f,%.3f,%.3f,%.2f,adaptive\n",
            millis(), pump_type.c_str(), old, dosing_system.ph_minus_coefficient,
            expected_change, observed_change, LEARNING_RATE);
    } else if (pump_type.startsWith("ec_sol") || pump_type == "ec_sol_total") {
        float old = dosing_system.ec_conductivity_coefficient;
        float new_coeff = old + LEARNING_RATE * (old * ratio - old);
        dosing_system.ec_conductivity_coefficient = constrain(new_coeff, 0.5, 10.0);
        Serial.printf("COEFFICIENT_UPDATE,%lu,%s,%.4f,%.4f,%.3f,%.3f,%.2f,adaptive\n",
            millis(), pump_type.c_str(), old, dosing_system.ec_conductivity_coefficient,
            expected_change, observed_change, LEARNING_RATE);
    } else if (pump_type == "h2o") {
        float old = dosing_system.h2o_dilution_coefficient;
        float new_coeff = old + LEARNING_RATE * (old * ratio - old);
        dosing_system.h2o_dilution_coefficient = constrain(new_coeff, 0.1, 5.0);
        Serial.printf("COEFFICIENT_UPDATE,%lu,%s,%.4f,%.4f,%.3f,%.3f,%.2f,adaptive\n",
            millis(), pump_type.c_str(), old, dosing_system.h2o_dilution_coefficient,
            expected_change, observed_change, LEARNING_RATE);
    }
}

// NEW: Record current cycle data for next cycle's learning (like Python system)
void recordCycleForLearning(int cycle_id, String pump_type, float volume_dosed, float expected_change, float current_ph, float current_ec) {
    if (!dosing_system.learning_enabled) {
        Serial.printf("LEARNING_DISABLED,%lu,skipping_record\n", millis());
        return;
    }
    
    // Record current cycle data for use in next cycle
    dosing_system.last_cycle_id = cycle_id;
    dosing_system.last_cycle_pump_type = pump_type;
    dosing_system.last_cycle_volume_dosed = volume_dosed;
    dosing_system.last_cycle_expected_change = expected_change;
    dosing_system.last_cycle_ph = current_ph;
    dosing_system.last_cycle_ec = current_ec;
    dosing_system.has_previous_cycle_data = true;
    
    Serial.printf("LEARNING_CYCLE_RECORDED,%lu,cycle,%d,%s,vol,%.2f,expected,%.3f,ph,%.2f,ec,%.2f\n",
        millis(), cycle_id, pump_type.c_str(), volume_dosed, expected_change, current_ph, current_ec);
}

// NEW: Apply learning from previous cycle (matching Python's approach)
void applyLearningFromPreviousCycle(int current_cycle_id, float current_ph, float current_ec) {
    // Only learn if we have previous cycle data AND this is a different cycle
    if (!dosing_system.has_previous_cycle_data || current_cycle_id <= dosing_system.last_cycle_id) {
        return;
    }
    
    Serial.printf("LEARNING_APPLICATION,%lu,prev_cycle,%d,curr_cycle,%d\n", 
        millis(), dosing_system.last_cycle_id, current_cycle_id);
    
    // Calculate observed changes from previous cycle's dosing
    float observed_ph_change = abs(current_ph - dosing_system.last_cycle_ph);
    float observed_ec_change = abs(current_ec - dosing_system.last_cycle_ec);
    
    Serial.printf("LEARNING_MEASUREMENT,%lu,%s,prev_ph,%.2f,curr_ph,%.2f,ph_change,%.3f\n",
        millis(), dosing_system.last_cycle_pump_type.c_str(), dosing_system.last_cycle_ph, current_ph, observed_ph_change);
    Serial.printf("LEARNING_MEASUREMENT,%lu,%s,prev_ec,%.2f,curr_ec,%.2f,ec_change,%.3f\n",
        millis(), dosing_system.last_cycle_pump_type.c_str(), dosing_system.last_cycle_ec, current_ec, observed_ec_change);
    
    // Apply learning based on pump type from previous cycle
    if (dosing_system.last_cycle_pump_type == "ph_plus" || dosing_system.last_cycle_pump_type == "ph_minus") {
        // pH learning - use pH change
        updateCoefficients(dosing_system.last_cycle_pump_type, dosing_system.last_cycle_expected_change, observed_ph_change);
        
    } else if (dosing_system.last_cycle_pump_type == "ec_sol_total" || dosing_system.last_cycle_pump_type.startsWith("ec_sol")) {
        // EC increase learning - use EC change
        updateCoefficients("ec_sol_total", dosing_system.last_cycle_expected_change, observed_ec_change);
        
    } else if (dosing_system.last_cycle_pump_type == "h2o") {
        // EC decrease learning - use EC change
        updateCoefficients("h2o", dosing_system.last_cycle_expected_change, observed_ec_change);
    }
    
    Serial.printf("LEARNING_APPLICATION_COMPLETE,%lu,cycle,%d,coefficients_updated\n", millis(), current_cycle_id);
}
