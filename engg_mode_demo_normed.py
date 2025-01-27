#!/usr/bin/env python3
#### engg_mode_demo_normed.py ####

import time
from radar_handler import RadarHandler
import sys
from typing import List
import numpy as np
from collections import deque

def interpret_measurements(moving_energies: List[int], static_energies: List[int]) -> str:
    """Interpret the energy patterns to describe what's being detected"""
    interpretation = []
    
    # Find peaks in moving and static energies
    moving_peak = max(moving_energies)
    static_peak = max(static_energies)
    
    moving_peak_dist = moving_energies.index(moving_peak) * 0.75
    static_peak_dist = static_energies.index(static_peak) * 0.75
    
    # Movement detection threshold
    MOVEMENT_THRESHOLD = 30
    STATIC_THRESHOLD = 40
    
    if moving_peak > MOVEMENT_THRESHOLD:
        interpretation.append(f"Movement detected at {moving_peak_dist:.1f}m (strength: {moving_peak}%)")
        
    if static_peak > STATIC_THRESHOLD:
        interpretation.append(f"Static presence at {static_peak_dist:.1f}m (strength: {static_peak}%)")
        
    # Look for multiple targets
    moving_targets = [i for i, e in enumerate(moving_energies) if e > MOVEMENT_THRESHOLD]
    static_targets = [i for i, e in enumerate(static_energies) if e > STATIC_THRESHOLD]
    
    if len(moving_targets) > 1:
        interpretation.append("Multiple moving targets detected")
    if len(static_targets) > 1:
        interpretation.append("Multiple static targets detected")
        
    return "\n".join(interpretation) if interpretation else "No significant targets detected"

class MovingAverage:
    def __init__(self, size: int = 3):
        self.size = size
        self.values = deque(maxlen=size)
        
    def add(self, value: float) -> float:
        self.values.append(value)
        return self.average
        
    @property
    def average(self) -> float:
        if not self.values:
            return 0
        return sum(self.values) / len(self.values)

def print_energy_bar(energy: int, width: int = 30) -> str:
    """Create a visual bar representation of energy level"""
    filled = int((energy / 100) * width)
    bar = '█' * filled + '░' * (width - filled)
    return f'[{bar}] {energy:3d}%'

def print_gate_data(name: str, energies: List[int], averages: List[MovingAverage], gate_size: float = 0.75):
    """Print formatted gate energy data with visualization"""
    print(f"\n{name} Energy Gates:")
    print("   Distance    Raw Energy         Smoothed")
    print("   --------    ----------         --------")
    max_energy = max(energies)
    peak_gate = energies.index(max_energy)
    
    for i, (energy, avg) in enumerate(zip(energies, averages)):
        dist = i * gate_size
        smoothed = int(avg.add(energy))
        raw_bar = print_energy_bar(energy, width=20)
        smooth_bar = print_energy_bar(smoothed, width=20)
        
        # Highlight peak values
        prefix = "→ " if i == peak_gate else "  "
        print(f"{prefix}{dist:4.1f}m:    {raw_bar}    {smooth_bar}")

def main():
    port = "/dev/ttyUSB0"  # Adjust as needed
    print(f"Initializing radar on port {port}...")
    
    radar = RadarHandler(port, debug=True)
    
    try:
        print("\nEnabling engineering mode...")
        attempts = 3
        success = False
        
        for i in range(attempts):
            success = radar.enable_engineering_mode()
            if success:
                break
            print(f"Attempt {i+1} failed, retrying...")
            time.sleep(1)
            
        if not success:
            print("Failed to enable engineering mode! Exiting...")
            radar.close()
            sys.exit(1)
        
        print("\nStarting data collection (Press Ctrl+C to exit)...")
        print("-" * 80)
        
        # Initialize moving averages for each possible gate
        MAX_GATES = 9
        moving_averages = [MovingAverage(size=5) for _ in range(MAX_GATES)]
        static_averages = [MovingAverage(size=5) for _ in range(MAX_GATES)]
        
        while True:
            reading = radar.read_frame()
            if reading and reading.is_valid():
                print(f"\033[2J\033[H")  # Clear screen and move to top
                print(f"Timestamp: {reading.timestamp:.2f}")
                print(f"Target State: {reading.target_state.name}")
                print(f"Detection Distance: {reading.detection_distance} cm")
                
                if reading.engineering_data:
                    try:
                        print_gate_data("Moving", 
                                      reading.engineering_data.moving_energy_gates,
                                      moving_averages)
                        print()
                        print_gate_data("Static", 
                                      reading.engineering_data.static_energy_gates,
                                      static_averages)
                        
                        # Add interpretation
                        print("\nRadar Interpretation:")
                        print("-" * 40)
                        interpretation = interpret_measurements(
                            reading.engineering_data.moving_energy_gates,
                            reading.engineering_data.static_energy_gates
                        )
                        print(interpretation)
                        
                    except Exception as e:
                        print(f"Error displaying data: {e}")
                
                print("\n" + "-" * 80)
            
            time.sleep(0.1)  # Small delay to prevent flooding the console
            
    except KeyboardInterrupt:
        print("\nDisabling engineering mode...")
        radar.disable_engineering_mode()
        radar.close()
        print("Radar connection closed")
    except Exception as e:
        print(f"\nError occurred: {e}")
        radar.close()
        sys.exit(1)

if __name__ == "__main__":
    main()
