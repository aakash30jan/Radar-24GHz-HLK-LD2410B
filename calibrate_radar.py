#!/usr/bin/env python3
#### calibrate_radar.py #### 

from radar_handler import RadarHandler, TargetState
import time
from typing import List, Tuple
import numpy as np

class RadarCalibrator:
    def __init__(self, port: str, baudrate: int = 256000):
        """Initialize the radar calibrator"""
        self.radar = RadarHandler(port, baudrate)
        self.original_settings = None  # Store original settings for restore
        
    def backup_settings(self):
        """Backup current radar settings"""
        if not self.radar.enable_configuration():
            return False
        
        # Read current parameters (command 0x0061)
        response = self.radar.send_command(bytes.fromhex('61 00'))
        if len(response) >= 30:  # Valid parameter response
            self.original_settings = response[8:-4]  # Store settings portion
            
        self.radar.end_configuration()
        return bool(self.original_settings)
        
    def restore_factory_defaults(self) -> bool:
        """Restore radar to factory default settings"""
        if not self.radar.enable_configuration():
            return False
            
        # Send factory reset command (0x00A2)
        response = self.radar.send_command(bytes.fromhex('A2 00'))
        success = len(response) >= 10 and response[8:10] == b'\x00\x00'
        
        if success:
            # Need to restart module for factory reset to take effect
            self.radar.send_command(bytes.fromhex('A3 00'))
            time.sleep(2)  # Wait for restart
            
        self.radar.end_configuration()
        return success
        
    def verify_placement(self) -> bool:
        """Verify proper radar placement before calibration"""
        print("\nPlacement Verification Checklist:")
        print("\nMounting:")
        print("1. Is the radar mounted at proper height? (1.5-2m for wall, ~3m for ceiling)")
        print("2. Is the radar mounted firmly with no vibration?")
        print("3. Is the radar oriented correctly? (straight, not tilted)")
        
        print("\nEnvironment:")
        print("4. Is the area in front of the radar clear of moving objects (curtains, plants)?")
        print("5. Are there any large reflective surfaces in the detection area?")
        print("6. Are there any air conditioners or fans above the radar?")
        print("7. Is the area behind the radar clear or shielded?")
        
        response = input("\nHave you verified all conditions? (yes/no): ").lower()
        return response == 'yes'
        
    def configure_detection_gates(self, moving_gate: int, static_gate: int) -> bool:
        """
        Configure the maximum detection distance gates
        Args:
            moving_gate: Maximum moving detection gate (1-8, each gate = 0.75m)
            static_gate: Maximum static detection gate (1-8, each gate = 0.75m)
        """
        if not (1 <= moving_gate <= 8 and 1 <= static_gate <= 8):
            print("Gates must be between 1 and 8")
            return False
            
        # Enter configuration mode
        if not self.radar.enable_configuration():
            return False
            
        # Command format for setting max gates (0x0060)
        command = bytes.fromhex('60 00')
        
        # Construct command value: moving gate + static gate + no-man time (default 5s)
        value = (
            bytes.fromhex('00 00') +  # moving gate parameter word
            moving_gate.to_bytes(4, 'little') +  # moving gate value
            bytes.fromhex('01 00') +  # static gate parameter word
            static_gate.to_bytes(4, 'little') +  # static gate value
            bytes.fromhex('02 00') +  # no-man time parameter word
            (5).to_bytes(4, 'little')  # no-man time value (5 seconds)
        )
        
        response = self.radar.send_command(command, value)
        success = len(response) >= 10 and response[8:10] == b'\x00\x00'
        
        self.radar.end_configuration()
        return success
        
    def configure_sensitivity(self, gate: int, motion_sensitivity: int, static_sensitivity: int) -> bool:
        """
        Configure sensitivity for a specific distance gate
        Args:
            gate: Distance gate number (0-8)
            motion_sensitivity: Motion detection sensitivity (0-100)
            static_sensitivity: Static detection sensitivity (0-100)
        """
        if not (0 <= gate <= 8):
            print("Gate must be between 0 and 8")
            return False
            
        if not (0 <= motion_sensitivity <= 100 and 0 <= static_sensitivity <= 100):
            print("Sensitivity must be between 0 and 100")
            return False
            
        # Enter configuration mode
        if not self.radar.enable_configuration():
            return False
            
        # Command format for setting sensitivity (0x0064)
        command = bytes.fromhex('64 00')
        
        # Construct command value
        value = (
            bytes.fromhex('00 00') +  # gate parameter word
            gate.to_bytes(4, 'little') +  # gate number
            bytes.fromhex('01 00') +  # motion sensitivity parameter word
            motion_sensitivity.to_bytes(4, 'little') +  # motion sensitivity value
            bytes.fromhex('02 00') +  # static sensitivity parameter word
            static_sensitivity.to_bytes(4, 'little')  # static sensitivity value
        )
        
        response = self.radar.send_command(command, value)
        success = len(response) >= 10 and response[8:10] == b'\x00\x00'
        
        self.radar.end_configuration()
        return success

    def calibrate_distance(self, actual_distances: List[float], samples_per_distance: int = 50) -> dict:
        """
        Calibrate distance measurements by comparing actual vs measured distances
        Args:
            actual_distances: List of actual distances to test (in cm)
            samples_per_distance: Number of samples to take at each distance
        Returns:
            Dictionary containing calibration results
        """
        calibration_data = {}
        
        print("Starting distance calibration...")
        print("Please place a person at each specified distance when prompted.")
        
        for distance in actual_distances:
            input(f"\nPlace person at {distance}cm and press Enter...")
            print(f"Taking {samples_per_distance} measurements...")
            
            measurements = []
            start_time = time.time()
            
            while len(measurements) < samples_per_distance:
                reading = self.radar.read_frame()
                if reading and reading.is_valid():
                    measurements.append(reading.detection_distance)
                time.sleep(0.1)
                
            measured_avg = np.mean(measurements)
            measured_std = np.std(measurements)
            
            calibration_data[distance] = {
                'measured_avg': measured_avg,
                'measured_std': measured_std,
                'error': measured_avg - distance,
                'error_percent': ((measured_avg - distance) / distance) * 100
            }
            
            print(f"Distance: {distance}cm")
            print(f"Measured: {measured_avg:.1f}cm ± {measured_std:.1f}cm")
            print(f"Error: {calibration_data[distance]['error']:.1f}cm ({calibration_data[distance]['error_percent']:.1f}%)")
            
        return calibration_data

    def find_optimal_sensitivity(self, distance: float, 
                               min_sensitivity: int = 0, 
                               max_sensitivity: int = 100,
                               samples: int = 30) -> Tuple[int, float]:
        """
        Find optimal sensitivity setting for a given distance
        Args:
            distance: Target distance to optimize for (in cm)
            min_sensitivity: Minimum sensitivity to test
            max_sensitivity: Maximum sensitivity to test
            samples: Number of samples to take for each sensitivity value
        Returns:
            Tuple of (optimal_sensitivity, detection_rate)
        """
        print(f"\nFinding optimal sensitivity for {distance}cm...")
        input("Place person at the specified distance and press Enter...")
        
        best_sensitivity = 0
        best_detection_rate = 0
        
        # Test range of sensitivity values
        for sensitivity in range(min_sensitivity, max_sensitivity + 1, 5):
            print(f"Testing sensitivity {sensitivity}...")
            
            # Configure sensitivity for all gates
            self.configure_sensitivity(0xFF, sensitivity, sensitivity)
            
            # Take measurements
            detections = 0
            measurements = []
            
            for _ in range(samples):
                reading = self.radar.read_frame()
                if reading and reading.is_valid():
                    if reading.target_state != TargetState.NO_TARGET:
                        detections += 1
                        measurements.append(reading.detection_distance)
                time.sleep(0.1)
            
            detection_rate = detections / samples
            
            if measurements:
                avg_distance = np.mean(measurements)
                distance_error = abs(avg_distance - distance)
                print(f"Detection rate: {detection_rate*100:.1f}%")
                print(f"Average distance: {avg_distance:.1f}cm (error: {distance_error:.1f}cm)")
            
            if detection_rate > best_detection_rate:
                best_detection_rate = detection_rate
                best_sensitivity = sensitivity
        
        return best_sensitivity, best_detection_rate

    def calibrate_full(self, distances: List[float]) -> dict:
        """
        Perform full calibration including distance and sensitivity
        Args:
            distances: List of distances to calibrate for (in cm)
        Returns:
            Dictionary containing full calibration results
        """
        # Verify proper placement first
        if not self.verify_placement():
            print("Please correct placement issues before calibrating.")
            return None
            
        # Backup current settings
        print("Backing up current settings...")
        if not self.backup_settings():
            print("Warning: Could not backup current settings")
            proceed = input("Continue anyway? (yes/no): ").lower()
            if proceed != 'yes':
                return None
        results = {
            'distance_calibration': {},
            'sensitivity_calibration': {}
        }
        
        # First calibrate distance measurements
        print("Step 1: Distance Calibration")
        results['distance_calibration'] = self.calibrate_distance(distances)
        
        # Then find optimal sensitivity for each distance
        print("\nStep 2: Sensitivity Calibration")
        for distance in distances:
            opt_sensitivity, detection_rate = self.find_optimal_sensitivity(distance)
            results['sensitivity_calibration'][distance] = {
                'optimal_sensitivity': opt_sensitivity,
                'detection_rate': detection_rate
            }
            
        return results

    def close(self):
        """Close the radar connection"""
        self.radar.close()

# Example usage:
if __name__ == "__main__":
    calibrator = RadarCalibrator("/dev/ttyUSB0")  # Adjust port as needed
    
    try:
        # Example calibration distances (in cm)
        calibration_distances = [75, 150, 225, 300]  # 0.75m, 1.5m, 2.25m, 3m
        
        # Perform full calibration
        results = calibrator.calibrate_full(calibration_distances)
        
        # Print results
        print("\nCalibration Results:")
        print("\nDistance Calibration:")
        for distance, data in results['distance_calibration'].items():
            print(f"\nDistance: {distance}cm")
            print(f"Average measured: {data['measured_avg']:.1f}cm")
            print(f"Standard deviation: {data['measured_std']:.1f}cm")
            print(f"Error: {data['error']:.1f}cm ({data['error_percent']:.1f}%)")
        
        print("\nSensitivity Calibration:")
        for distance, data in results['sensitivity_calibration'].items():
            print(f"\nDistance: {distance}cm")
            print(f"Optimal sensitivity: {data['optimal_sensitivity']}")
            print(f"Detection rate: {data['detection_rate']*100:.1f}%")
            
    finally:
        calibrator.close()
