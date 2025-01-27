#!/usr/bin/env python3
#### radar_visualizer.py #### 

import numpy as np
import matplotlib.pyplot as plt
from radar_handler import RadarHandler
import time
from collections import deque
import math

class RadarVisualizer:
    def __init__(self, max_history=10):
        # Initialize radar
        self.radar = RadarHandler("/dev/ttyUSB0", debug=False)
        
        # Setup visualization
        plt.ion()  # Enable interactive mode
        self.fig, self.ax = plt.subplots(figsize=(10, 10))
        self.max_history = max_history
        
        # Track motion paths - store (time, distance, energy) tuples
        self.motion_path = deque(maxlen=max_history)
        self.last_significant_motion = None
        
        # Setup plot parameters
        self.max_range = 6.0  # meters
        self.angle_range = 120  # degrees (-60 to +60)
        self.min_angle = -60  # degrees
        self.max_angle = 60   # degrees
        
        # Constants
        self.MOTION_THRESHOLD = 30
        self.STATIC_THRESHOLD = 40
        self.MIN_MOVEMENT = 0.3  # minimum movement to be considered real motion (meters)
        
    def setup_plot(self):
        """Setup the radar plot area"""
        self.ax.clear()
        
        # Draw radar detection area (120-degree arc)
        angle = np.linspace(self.min_angle, self.max_angle, 100)
        x = self.max_range * np.cos(np.radians(angle))
        y = self.max_range * np.sin(np.radians(angle))
        self.ax.plot(x, y, 'k--', alpha=0.3)
        
        # Draw range circles but only show the right half
        for r in range(1, int(self.max_range) + 1):
            # Create a partial circle from -60 to +60 degrees
            angle = np.linspace(self.min_angle, self.max_angle, 100)
            x = r * np.cos(np.radians(angle))
            y = r * np.sin(np.radians(angle))
            self.ax.plot(x, y, 'gray', alpha=0.2)
        
        # Set plot properties - only show the relevant area
        self.ax.set_xlim(-self.max_range/2, self.max_range + 0.5)
        self.ax.set_ylim(-0.5, self.max_range + 0.5)
        self.ax.grid(True, alpha=0.3)
        self.ax.set_aspect('equal')
        self.ax.set_title("Radar View")
        
        # Add radar position marker
        self.ax.plot(0, 0, 'k^', markersize=10, label='Radar')
        
    def find_peak_motion(self, moving_data):
        """Find the strongest motion signal"""
        max_energy = max(moving_data)
        if max_energy > self.MOTION_THRESHOLD:
            distance = moving_data.index(max_energy) * 0.75
            return distance, max_energy
        return None, None
        
    def plot_motion_path(self):
        """Plot the motion path with fading colors"""
        if len(self.motion_path) < 2:
            return
            
        # Convert motion path to arrays for plotting
        times, distances, energies = zip(*self.motion_path)
        
        # Normalize times to 0-1 for color gradient
        times = np.array(times)
        min_time, max_time = min(times), max(times)
        norm_times = (times - min_time) / (max_time - min_time) if max_time > min_time else times
        
        # Plot path
        for i in range(len(distances) - 1):
            # Calculate angle based on motion direction
            angle = 0  # Default straight ahead
            if i > 0 and abs(distances[i] - distances[i-1]) > self.MIN_MOVEMENT:
                angle = 15 if distances[i] > distances[i-1] else -15
                
            x1, y1 = self.polar_to_cartesian(distances[i], angle)
            x2, y2 = self.polar_to_cartesian(distances[i+1], angle)
            
            # Plot line segment with fading color
            alpha = norm_times[i]
            self.ax.plot([x1, x2], [y1, y2], 'r-', alpha=alpha, linewidth=2)
            
            # Plot point with size based on energy
            size = energies[i] / 2
            self.ax.plot(x1, y1, 'r*', alpha=alpha, markersize=size)
        
    def polar_to_cartesian(self, distance, angle_deg):
        """Convert polar coordinates to cartesian"""
        angle_rad = math.radians(angle_deg)
        x = distance * math.cos(angle_rad)
        y = distance * math.sin(angle_rad)
        return x, y
        
    def run(self):
        """Main visualization loop"""
        try:
            print("Enabling engineering mode...")
            if not self.radar.enable_engineering_mode():
                print("Failed to enable engineering mode!")
                return
                
            while True:
                reading = self.radar.read_frame()
                if reading and reading.is_valid() and reading.engineering_data:
                    self.setup_plot()
                    
                    # Process moving targets
                    moving_data = reading.engineering_data.moving_energy_gates
                    static_data = reading.engineering_data.static_energy_gates
                    
                    # Find significant motion
                    distance, energy = self.find_peak_motion(moving_data)
                    current_time = time.time()
                    
                    if distance is not None:
                        # Add to motion path if significant movement detected
                        self.motion_path.append((current_time, distance, energy))
                        self.last_significant_motion = current_time
                    elif self.last_significant_motion and \
                         current_time - self.last_significant_motion > 1.0:
                        # Clear path if no motion for 1 second
                        self.motion_path.clear()
                        self.last_significant_motion = None
                    
                    # Plot the motion path
                    self.plot_motion_path()
                    
                    # Plot static objects
                    for i, energy in enumerate(static_data):
                        if energy > self.STATIC_THRESHOLD:
                            distance = i * 0.75
                            x, y = self.polar_to_cartesian(distance, 0)
                            size = energy / 2
                            self.ax.plot(x, y, 'bo', alpha=0.3, markersize=size)
                    
                    plt.draw()
                    plt.pause(0.1)
                    
        except KeyboardInterrupt:
            print("\nStopping visualization...")
            self.radar.disable_engineering_mode()
            self.radar.close()
            plt.close()

if __name__ == "__main__":
    visualizer = RadarVisualizer()
    visualizer.run()
