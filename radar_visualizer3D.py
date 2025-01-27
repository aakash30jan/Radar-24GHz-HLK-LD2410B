#!/usr/bin/env python3
#### radar_visualizer3D.py #### 

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from radar_handler import RadarHandler
import time
from collections import deque
import math

class Radar3DVisualizer:
    def __init__(self, max_history=50):
        # Initialize radar
        self.radar = RadarHandler("/dev/ttyUSB0", debug=False)
        
        # Setup visualization
        plt.ion()  # Enable interactive mode
        self.fig = plt.figure(figsize=(15, 10))
        
        # Create two subplots: 2D top view and 3D view
        self.ax_2d = self.fig.add_subplot(121)
        self.ax_3d = self.fig.add_subplot(122, projection='3d')
        
        self.max_history = max_history
        self.motion_path = deque(maxlen=max_history)
        self.last_significant_motion = None
        
        # Radar parameters
        self.max_range = 6.0  # meters
        self.angle_range = 120  # degrees (-60 to +60)
        self.min_angle = -60
        self.max_angle = 60
        self.mounting_height = 2.0  # meters
        
        # Detection thresholds
        self.MOTION_THRESHOLD = 30
        self.STATIC_THRESHOLD = 40
        self.MIN_MOVEMENT = 0.3
        
        # Expected path parameters
        self.expected_path = self.generate_expected_path()
        
    def generate_expected_path(self):
        """Generate expected straight-line walking path with reference points"""
        # Generate main path points
        distances = np.linspace(self.max_range, 0.5, 20)
        
        # Create reference points every 0.75m (matching radar gates)
        ref_distances = np.arange(0.75, self.max_range, 0.75)
        
        # Expected heights for different parts of human body
        head_height = 1.7  # Average human height
        shoulder_height = 1.5
        torso_height = 1.2
        
        # Generate points for different body heights
        path_points = []
        for d in distances:
            # Add points at different heights to represent human body
            path_points.extend([
                (d, 0, head_height),     # Head level
                (d, 0, shoulder_height),  # Shoulder level
                (d, 0, torso_height)      # Torso level
            ])
            
        # Add reference points
        ref_points = []
        for d in ref_distances:
            ref_points.extend([
                (d, 0, head_height),
                (d, 0, shoulder_height),
                (d, 0, torso_height)
            ])
            
        return path_points, ref_points
        
    def setup_2d_plot(self):
        """Setup the 2D radar plot"""
        self.ax_2d.clear()
        
        # Draw detection area
        angle = np.linspace(self.min_angle, self.max_angle, 100)
        x = self.max_range * np.cos(np.radians(angle))
        y = self.max_range * np.sin(np.radians(angle))
        self.ax_2d.plot(x, y, 'k--', alpha=0.3)
        
        # Draw range circles
        for r in range(1, int(self.max_range) + 1):
            angle = np.linspace(self.min_angle, self.max_angle, 100)
            x = r * np.cos(np.radians(angle))
            y = r * np.sin(np.radians(angle))
            self.ax_2d.plot(x, y, 'gray', alpha=0.2)
        
        # Plot expected path in 2D (using only head height points for clarity)
        path_points, ref_points = self.expected_path
        head_points = [(d, a) for d, a, h in path_points if h == 1.7]  # Filter head height points
        if head_points:
            exp_x = [d * np.cos(np.radians(a)) for d, a in head_points]
            exp_y = [d * np.sin(np.radians(a)) for d, a in head_points]
            self.ax_2d.plot(exp_x, exp_y, 'g--', label='Expected Path')
        
        # Plot reference points
        ref_head_points = [(d, a) for d, a, h in ref_points if h == 1.7]
        if ref_head_points:
            ref_x = [d * np.cos(np.radians(a)) for d, a in ref_head_points]
            ref_y = [d * np.sin(np.radians(a)) for d, a in ref_head_points]
            self.ax_2d.scatter(ref_x, ref_y, c='green', marker='o', s=50, alpha=0.5)
        
        self.ax_2d.set_xlim(-self.max_range/2, self.max_range + 0.5)
        self.ax_2d.set_ylim(-0.5, self.max_range + 0.5)
        self.ax_2d.grid(True, alpha=0.3)
        self.ax_2d.set_aspect('equal')
        self.ax_2d.set_title("Top View")
        self.ax_2d.plot(0, 0, 'k^', markersize=10, label='Radar')
        
    def setup_3d_plot(self):
        """Setup the 3D visualization"""
        self.ax_3d.clear()
        
        # Plot radar cone in 3D
        theta = np.linspace(-np.pi/3, np.pi/3, 30)
        r = np.linspace(0, self.max_range, 30)
        T, R = np.meshgrid(theta, r)
        
        X = R * np.cos(T)
        Y = R * np.sin(T)
        Z = np.zeros_like(X)
        
        self.ax_3d.plot_surface(X, Y, Z, alpha=0.1, color='gray')
        
        # Plot expected path and reference points
        path_points, ref_points = self.expected_path
        
        # Plot continuous expected path
        for height in [1.7, 1.5, 1.2]:  # Head, shoulder, torso heights
            path_x = [d * np.cos(np.radians(a)) for d, a, h in path_points if h == height]
            path_y = [d * np.sin(np.radians(a)) for d, a, h in path_points if h == height]
            path_z = [h for _, _, h in path_points if h == height]
            self.ax_3d.plot(path_x, path_y, path_z, 'g-', alpha=0.3, linewidth=1)
        
        # Plot reference points (radar gates)
        ref_x = [d * np.cos(np.radians(a)) for d, a, h in ref_points]
        ref_y = [d * np.sin(np.radians(a)) for d, a, h in ref_points]
        ref_z = [h for _, _, h in ref_points]
        self.ax_3d.scatter(ref_x, ref_y, ref_z, c='green', marker='o', s=50, alpha=0.5, label='Expected Detection Points')
        
        # Add vertical reference lines at each gate
        for d in np.arange(0.75, self.max_range, 0.75):
            self.ax_3d.plot([d, d], [0, 0], [0, 1.7], 'g:', alpha=0.2)
        
        # Set 3D plot properties
        self.ax_3d.set_xlim(-self.max_range/2, self.max_range)
        self.ax_3d.set_ylim(-self.max_range/2, self.max_range)
        self.ax_3d.set_zlim(0, 3)
        self.ax_3d.set_title("3D View")
        self.ax_3d.set_xlabel("X (m)")
        self.ax_3d.set_ylabel("Y (m)")
        self.ax_3d.set_zlabel("Height (m)")
        
    def plot_motion_path(self):
        """Plot the detected motion path in both 2D and 3D"""
        if len(self.motion_path) < 2:
            return
            
        times, distances, angles, energies = zip(*self.motion_path)
        
        # Calculate positions
        x_pos = [d * np.cos(np.radians(a)) for d, a in zip(distances, angles)]
        y_pos = [d * np.sin(np.radians(a)) for d, a in zip(distances, angles)]
        z_pos = [1.7 + e/100 for e in energies]  # Vary height slightly based on energy
        
        # Plot in 2D
        for i in range(len(x_pos) - 1):
            alpha = (i + 1) / len(x_pos)
            self.ax_2d.plot([x_pos[i], x_pos[i+1]], [y_pos[i], y_pos[i+1]], 
                          'r-', alpha=alpha, linewidth=2)
            self.ax_2d.plot(x_pos[i], y_pos[i], 'r*', alpha=alpha, 
                          markersize=energies[i]/2)
        
        # Plot in 3D
        self.ax_3d.plot(x_pos, y_pos, z_pos, 'r-', label='Detected Path')
        for i in range(len(x_pos)):
            alpha = (i + 1) / len(x_pos)
            self.ax_3d.scatter(x_pos[i], y_pos[i], z_pos[i], c='red', 
                             alpha=alpha, s=energies[i])
        
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
                    self.setup_2d_plot()
                    self.setup_3d_plot()
                    
                    # Process moving targets
                    moving_data = reading.engineering_data.moving_energy_gates
                    
                    # Find peak motion
                    max_energy = max(moving_data)
                    if max_energy > self.MOTION_THRESHOLD:
                        distance = moving_data.index(max_energy) * 0.75
                        # Estimate angle based on movement
                        angle = 0  # Default straight approach
                        if self.motion_path:
                            last_dist = self.motion_path[-1][1]
                            angle = 15 if distance > last_dist else -15
                            
                        self.motion_path.append((time.time(), distance, angle, max_energy))
                        self.last_significant_motion = time.time()
                    elif self.last_significant_motion and \
                         time.time() - self.last_significant_motion > 1.0:
                        self.motion_path.clear()
                        self.last_significant_motion = None
                    
                    self.plot_motion_path()
                    
                    plt.draw()
                    plt.pause(0.1)
                    
        except KeyboardInterrupt:
            print("\nStopping visualization...")
            self.radar.disable_engineering_mode()
            self.radar.close()
            plt.close()

if __name__ == "__main__":
    visualizer = Radar3DVisualizer()
    visualizer.run()
