#!/usr/bin/env python3
#### radar_handler.py ####

import serial
from dataclasses import dataclass
from typing import Optional, Tuple
import time
from enum import Enum
import numpy as np

class TargetState(Enum):
    NO_TARGET = 0
    MOVING_TARGET = 1
    STATIC_TARGET = 2
    BOTH_TARGETS = 3
    UNKNOWN = 4

@dataclass
class RadarReading:
    timestamp: float
    target_state: TargetState
    moving_target_distance: int
    moving_target_energy: int
    static_target_distance: int
    static_target_energy: int
    detection_distance: int

    def is_valid(self) -> bool:
        """Check if the radar reading contains valid data"""
        return (
            0 <= self.detection_distance <= 600 and  # Max 6m detection range
            -100 <= self.moving_target_energy <= 100 and
            -100 <= self.static_target_energy <= 100 and
            self.target_state != TargetState.UNKNOWN
        )

@dataclass
class EngineeringData:
    """Engineering mode data containing energy values for each distance gate"""
    max_moving_distance_gate: int
    max_static_distance_gate: int
    moving_energy_gates: list[int]  # Energy values for each moving distance gate
    static_energy_gates: list[int]  # Energy values for each static distance gate

@dataclass
class RadarReading:
    timestamp: float
    target_state: TargetState
    moving_target_distance: int
    moving_target_energy: int
    static_target_distance: int
    static_target_energy: int
    detection_distance: int
    engineering_data: Optional[EngineeringData] = None

    def is_valid(self) -> bool:
        """Check if the radar reading contains valid data"""
        return (
            0 <= self.detection_distance <= 600 and  # Max 6m detection range
            -100 <= self.moving_target_energy <= 100 and
            -100 <= self.static_target_energy <= 100 and
            self.target_state != TargetState.UNKNOWN
        )

class RadarHandler:
    COMMAND_HEADER = bytes.fromhex('FD FC FB FA')
    COMMAND_TAIL = bytes.fromhex('04 03 02 01')
    REPORT_HEADER = bytes.fromhex('F4 F3 F2 F1')
    REPORT_TAIL = bytes.fromhex('F8 F7 F6 F5')

    def __init__(self, port: str, baudrate: int = 256000, debug: bool = False):
        """Initialize radar handler with serial port settings"""
        self.serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=1,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE
        )
        self.readings_buffer = []
        self.max_buffer_size = 1000
        self.engineering_mode = False
        self.debug = debug
        
        # Clear any pending data
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        
    def _debug_print(self, *args, **kwargs):
        """Print debug information if debug mode is enabled"""
        if self.debug:
            print("DEBUG:", *args, **kwargs)
        
    def send_command(self, command_word: bytes, command_value: bytes = b'') -> bytes:
        """Send a command and get response"""
        # Calculate intra-frame length (command word + command value)
        intra_frame_length = len(command_word) + len(command_value)
        
        # Construct full command
        command = (
            self.COMMAND_HEADER +
            intra_frame_length.to_bytes(2, byteorder='little') +
            command_word +
            command_value +
            self.COMMAND_TAIL
        )
        
        # Clear input buffer
        self.serial.reset_input_buffer()
        time.sleep(0.1)  # Add small delay for stability
        
        # Send command and get response
        if self.debug:
            print(f"Sending command: {command.hex()}")
        self.serial.write(command)
        
        # Wait for and read response
        response = self.serial.read_until(self.COMMAND_TAIL, size=100)
        if self.debug:
            print(f"Received response: {response.hex()}")
            
        if len(response) < 12:  # Minimum valid response length
            if self.debug:
                print("Response too short")
            return b''
            
        return response

    def enable_configuration(self) -> bool:
        """Enable configuration mode"""
        # Command as per section 2.2.1 of documentation
        response = self.send_command(bytes.fromhex('FF 00'), bytes.fromhex('01 00'))
        
        # Check if we got a valid response
        if len(response) < 12:  # Minimum expected response length
            return False
            
        # Response should contain status (0 = success)
        status = int.from_bytes(response[8:10], byteorder='little')
        return status == 0

    def end_configuration(self) -> bool:
        """End configuration mode"""
        # Command as per section 2.2.2 of documentation
        response = self.send_command(bytes.fromhex('FE 00'))
        
        if len(response) < 12:
            return False
            
        status = int.from_bytes(response[8:10], byteorder='little')
        return status == 0

    def enable_engineering_mode(self) -> bool:
        """Enable engineering mode to get detailed gate data"""
        print("Entering configuration mode...")
        if not self.enable_configuration():
            print("Failed to enter configuration mode")
            return False
            
        print("Configuration mode enabled, setting engineering mode...")
        # Command as per section 2.2.5 of documentation
        response = self.send_command(bytes.fromhex('62 00'))
        
        # Check response
        if len(response) < 12:
            print("Invalid response length")
            self.end_configuration()
            return False
            
        status = int.from_bytes(response[8:10], byteorder='little')
        if status == 0:
            self.engineering_mode = True
            print("Engineering mode enabled successfully")
        else:
            print(f"Failed to enable engineering mode, status: {status}")
            
        print("Ending configuration mode...")
        self.end_configuration()
        return status == 0

    def disable_engineering_mode(self) -> bool:
        """Disable engineering mode"""
        if self.enable_configuration():
            command = (
                self.COMMAND_HEADER +
                int(2).to_bytes(2, byteorder='little') +
                bytes.fromhex('63 00') +
                self.COMMAND_TAIL
            )
            self.serial.write(command)
            response = self.serial.read_until(self.COMMAND_TAIL)
            success = int.from_bytes(response[8:10], byteorder='little') == 0
            if success:
                self.engineering_mode = False
            self.end_configuration()
            return success
        return False
        
    def _parse_target_state(self, state_byte: int) -> TargetState:
        """Convert raw state byte to TargetState enum"""
        try:
            return TargetState(state_byte)
        except ValueError:
            return TargetState.UNKNOWN

    def read_frame(self) -> Optional[RadarReading]:
        """Read and parse a single frame from the radar"""
        try:
            serial_line = self.serial.read_until(self.REPORT_TAIL)
            if not (self.REPORT_HEADER in serial_line and self.REPORT_TAIL in serial_line):
                return None

            # Extract target data (skipping headers)
            target_data = serial_line[8:-6]
            
            # Basic mode data is 9 bytes, engineering mode data is longer
            if len(target_data) < 9:
                return None
                
            # Parse basic data first
            basic_data = target_data[:9]

            engineering_data = None
            if self.engineering_mode and len(target_data) > 9:
                eng_data = target_data[9:]
                # First two bytes are max gates
                max_moving_gate = eng_data[0]
                max_static_gate = eng_data[1]
                
                # Next bytes are energy values for each gate
                moving_energies = []
                static_energies = []
                
                # Parse energy values for each gate
                offset = 2
                for i in range(max_moving_gate + 1):
                    if offset + i < len(eng_data):
                        moving_energies.append(eng_data[offset + i])
                
                offset += max_moving_gate + 1
                for i in range(max_static_gate + 1):
                    if offset + i < len(eng_data):
                        static_energies.append(eng_data[offset + i])
                
                engineering_data = EngineeringData(
                    max_moving_distance_gate=max_moving_gate,
                    max_static_distance_gate=max_static_gate,
                    moving_energy_gates=moving_energies,
                    static_energy_gates=static_energies
                )

            reading = RadarReading(
                timestamp=time.time(),
                target_state=self._parse_target_state(basic_data[0]),
                moving_target_distance=int.from_bytes(basic_data[1:3], byteorder='little', signed=True),
                moving_target_energy=int.from_bytes(basic_data[3:4], byteorder='little', signed=True),
                static_target_distance=int.from_bytes(basic_data[4:6], byteorder='little', signed=True),
                static_target_energy=int.from_bytes(basic_data[6:7], byteorder='little', signed=True),
                detection_distance=abs(int.from_bytes(basic_data[7:9], byteorder='little', signed=True)),
                engineering_data=engineering_data
            )

            if reading.is_valid():
                self.readings_buffer.append(reading)
                if len(self.readings_buffer) > self.max_buffer_size:
                    self.readings_buffer.pop(0)
                return reading
            return None

        except Exception as e:
            print(f"Error reading frame: {e}")
            return None

    def get_average_distance(self, window_size: int = 10) -> float:
        """Calculate moving average of detection distance"""
        if not self.readings_buffer:
            return 0.0
        recent_readings = self.readings_buffer[-window_size:]
        return np.mean([r.detection_distance for r in recent_readings])

    def get_motion_status(self, window_size: int = 5) -> Tuple[bool, bool]:
        """Analyze recent readings to determine if there's consistent motion or static presence"""
        if len(self.readings_buffer) < window_size:
            return False, False

        recent_readings = self.readings_buffer[-window_size:]
        motion_detected = any(r.target_state in [TargetState.MOVING_TARGET, TargetState.BOTH_TARGETS] 
                            for r in recent_readings)
        static_detected = any(r.target_state in [TargetState.STATIC_TARGET, TargetState.BOTH_TARGETS]
                            for r in recent_readings)
        
        return motion_detected, static_detected

    def close(self):
        """Close the serial connection"""
        self.serial.close()
