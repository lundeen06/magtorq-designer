import numpy as np
from dataclasses import dataclass
from scipy.optimize import minimize, fsolve
from typing import Dict, Any
import plotly.graph_objects as go
import webbrowser
import os
import json


@dataclass
class PCBConfig:
    """Configuration loaded from JSON file"""
    # Physical constants
    vacuum_permeability: float
    copper_resistivity: float
    temperature_coefficient: float
    oz_to_m: float
    current_density_limit: float
    
    # Thermal properties
    thermal_conductivity_copper: float
    thermal_conductivity_fr4: float
    fr4_thickness: float
    surface_area_multiplier: float
    
    # Design constraints
    num_layers: int
    copper_weight: float
    max_power: float
    voltage: float
    inner_length: float
    inner_width: float
    outer_length: float
    outer_width: float
    operating_temp: float
    ambient_temp: float
    
    # Manufacturing constraints
    min_trace_width: float
    max_trace_width: float
    min_trace_spacing: float
    
    @classmethod
    def from_json(cls, config: Dict[str, Any]) -> 'PCBConfig':
        """Create PCBConfig from JSON dictionary"""
        return cls(
            # Physical constants
            vacuum_permeability=config['physical_constants']['vacuum_permeability'],
            copper_resistivity=config['physical_constants']['copper_resistivity'],
            temperature_coefficient=config['physical_constants']['temperature_coefficient'],
            oz_to_m=config['physical_constants']['oz_to_m'],
            current_density_limit=config['physical_constants']['current_density_limit'],
            
            # Thermal properties
            thermal_conductivity_copper=config['thermal_properties']['thermal_conductivity_copper'],
            thermal_conductivity_fr4=config['thermal_properties']['thermal_conductivity_fr4'],
            fr4_thickness=config['thermal_properties']['fr4_thickness'],
            surface_area_multiplier=config['thermal_properties']['surface_area_multiplier'],
            
            # Design constraints
            num_layers=config['design_constraints']['num_layers'],
            copper_weight=config['design_constraints']['copper_weight'],
            max_power=config['design_constraints']['max_power'],
            voltage=config['design_constraints']['voltage'],
            inner_length=config['design_constraints']['inner_length'],
            inner_width=config['design_constraints']['inner_width'],
            outer_length=config['design_constraints']['outer_length'],
            outer_width=config['design_constraints']['outer_width'],
            operating_temp=config['design_constraints']['operating_temp'],
            ambient_temp=config['design_constraints']['ambient_temp'],
            
            # Manufacturing constraints
            min_trace_width=config['manufacturing_constraints']['min_trace_width'],
            max_trace_width=config['manufacturing_constraints']['max_trace_width'],
            min_trace_spacing=config['manufacturing_constraints']['min_trace_spacing']
        )

class MagnetorquerDesigner:
    def __init__(self, config: PCBConfig):
        self.config = config
        self.copper_thickness = config.copper_weight * config.oz_to_m
        self.coil_layers = config.num_layers - 1  # One layer for connections
        
    def calculate_max_turns(self, trace_width: float) -> int:
        """Calculate maximum number of turns given trace width"""
        if trace_width <= 0:
            return 0
            
        # Reduce inner clearance needed - only need space for one trace and gap on each side
        min_inner_clearance = trace_width + 2 * self.config.min_trace_spacing  # Changed from 2 * (trace_width + 2 * spacing)
        
        # Calculate available space
        effective_inner_length = self.config.inner_length + 2 * min_inner_clearance
        effective_inner_width = self.config.inner_width + 2 * min_inner_clearance
        
        available_height = (self.config.outer_length - effective_inner_length) / 2
        available_width = (self.config.outer_width - effective_inner_width) / 2
        
        if available_height <= 0 or available_width <= 0:
            return 0
        
        # Each turn needs space for trace and spacing
        turn_pitch = trace_width + self.config.min_trace_spacing
        
        # Use the more constraining dimension
        max_turns_height = int(available_height / turn_pitch)
        max_turns_width = int(available_width / turn_pitch)
        return max(1, min(max_turns_height, max_turns_width))

    def calculate_turn_length(self, turn_number: int, trace_width: float) -> float:
        """Calculate length of a specific turn including connections"""
        offset = turn_number * (trace_width + self.config.min_trace_spacing)
        
        # Current rectangle dimensions
        current_length = self.config.outer_length - 2 * offset
        current_width = self.config.outer_width - 2 * offset
        
        # Main rectangular path
        perimeter = 2 * (current_length + current_width)
        
        # Add connection to next turn
        if turn_number < self.calculate_max_turns(trace_width) - 1:
            connection_length = trace_width + self.config.min_trace_spacing
        else:
            connection_length = trace_width + self.config.min_trace_spacing
            
        return perimeter + connection_length

    def calculate_area(self, turn_number: int, trace_width: float) -> float:
        """Calculate area enclosed by a specific turn"""
        offset = turn_number * (trace_width + self.config.min_trace_spacing)
        length = self.config.outer_length - 2 * offset
        width = self.config.outer_width - 2 * offset
        return length * width

    def calculate_resistance(self, trace_width: float) -> float:
        """Calculate total resistance of coil"""
        num_turns = self.calculate_max_turns(trace_width)
        if num_turns <= 0 or trace_width <= 0:
            return np.inf
            
        total_length = sum(self.calculate_turn_length(turn, trace_width) 
                          for turn in range(num_turns))
        total_length *= self.coil_layers
        
        cross_section = self.copper_thickness * trace_width
        return self.config.copper_resistivity * total_length / cross_section

    def calculate_current(self, resistance: float, trace_width: float) -> float:
        """Calculate current given voltage, power, and current density constraints"""
        if resistance <= 0:
            return 0
        
        # Calculate maximum current from power limit
        # P = IV -> I = P/V
        max_current_from_power = self.config.max_power / self.config.voltage
        
        # Calculate maximum current from current density limit
        # J = I/A where A is cross-sectional area
        cross_section = trace_width * self.copper_thickness
        max_current_from_density = self.config.current_density_limit * cross_section
        
        # Calculate current from Ohm's law
        current_from_resistance = self.config.voltage / resistance
        
        # Take minimum of all constraints
        current = min(current_from_resistance, 
                    max_current_from_power,
                    max_current_from_density)
        
        return current

    def calculate_temperature_rise(self, power: float) -> float:
        """Calculate temperature rise in space (radiation only)"""
        # Stefan-Boltzmann constant
        stefan_boltzmann = 5.67e-8  # W/(m²·K⁴)
        
        # Radiating area (both sides of board)
        area = self.config.surface_area_multiplier * self.config.outer_length * self.config.outer_width
        
        # Space temperature (0°C in Kelvin)
        T_space = 273.15
        
        # Solve heat balance equation: P = εσA(T⁴ - T_space⁴)
        def heat_balance(T):
            radiation = (0.9 * stefan_boltzmann * area * (T**4 - T_space**4))
            return radiation - power
            
        T_final = fsolve(heat_balance, T_space + 5)[0]
        return T_final - T_space
    
    def calculate_inductance(self, trace_width: float) -> float:
        """Calculate approximate inductance of the PCB coil using Wheeler's formula"""
        num_turns = self.calculate_max_turns(trace_width)
        if num_turns <= 0:
            return 0
            
        # Calculate average diameter (in meters)
        avg_length = (self.config.outer_length + self.config.inner_length) / 2
        avg_width = (self.config.outer_width + self.config.inner_width) / 2
        avg_diameter = (avg_length + avg_width) / 2
        
        # Wheeler's formula for rectangular coils (modified for multiple layers)
        # L = K1 * μ0 * N² * davg * (ln(4*davg/w) - 0.5)
        # where K1 is an empirical constant ≈ 0.4, N is number of turns, davg is average diameter
        # and w is the trace width
        K1 = 0.4
        inductance = (K1 * self.config.vacuum_permeability * (num_turns * self.coil_layers)**2 * 
                     avg_diameter * (np.log(4 * avg_diameter / trace_width) - 0.5))
        
        return inductance

    def calculate_time_constant(self, trace_width: float) -> float:
        """Calculate the RL time constant (tau = L/R)"""
        inductance = self.calculate_inductance(trace_width)
        resistance = self.calculate_resistance(trace_width)
        
        if resistance <= 0:
            return 0
            
        return inductance / resistance

    def calculate_time_to_percentage(self, trace_width: float, target_percentage: float) -> float:
        """Calculate time to reach a target percentage of final value"""
        tau = self.calculate_time_constant(trace_width)
        # Using the formula: percentage = 1 - e^(-t/tau)
        # Solving for t: t = -tau * ln(1 - percentage)
        return -tau * np.log(1 - target_percentage)

    def calculate_magnetic_moment(self, trace_width: float, current: float) -> float:
        """Calculate magnetic moment of coil"""
        num_turns = self.calculate_max_turns(trace_width)
        if num_turns <= 0 or current <= 0:
            return 0
        
        total_area = sum(self.calculate_area(turn, trace_width) 
                        for turn in range(num_turns))
        return total_area * current * self.coil_layers

    def check_constraints(self, trace_width: float) -> bool:
        """Check all design constraints"""
        if (trace_width < self.config.min_trace_width or 
            trace_width > self.config.max_trace_width):
            return False
            
        resistance = self.calculate_resistance(trace_width)
        current = self.calculate_current(resistance, trace_width) 
        
        # Check current density limit
        current_density = current / (trace_width * self.copper_thickness)
        if current_density > self.config.current_density_limit:
            return False
            
        # Check thermal limit
        power = current * self.config.voltage
        temp_rise = self.calculate_temperature_rise(power)
        if temp_rise > (self.config.operating_temp - self.config.ambient_temp):
            return False
            
        return True

    def optimize(self, num_points: int = 1000) -> tuple[dict, list, list, list]:
        """
        Run optimization and collect data for both plots
        
        Args:
            num_points: Number of points to evaluate between min and max width
        
        Returns:
            tuple: (analysis results dict, width data, moment_vs_width data, moment_vs_current data)
        """
        # Create evenly spaced points using numpy
        widths_array = np.linspace(
            self.config.min_trace_width,
            self.config.max_trace_width,
            num_points
        )
        
        # Initialize arrays
        moments_array = np.zeros_like(widths_array)
        currents_array = np.zeros_like(widths_array)
        valid_designs = np.zeros_like(widths_array, dtype=bool)
        
        # Collect data
        for i, width in enumerate(widths_array):
            if self.check_constraints(width):
                resistance = self.calculate_resistance(width)
                current = self.calculate_current(resistance, width)
                moment = self.calculate_magnetic_moment(width, current)
                
                moments_array[i] = moment
                currents_array[i] = current
                valid_designs[i] = True
        
        # Filter out invalid designs
        valid_widths = widths_array[valid_designs]
        valid_moments = moments_array[valid_designs]
        valid_currents = currents_array[valid_designs]
        
        # Find optimal point
        if len(valid_moments) > 0:
            best_idx = np.argmax(valid_moments)
            best_width = valid_widths[best_idx]
            best_current = valid_currents[best_idx]
            best_moment = valid_moments[best_idx]
        else:
            best_width = self.config.min_trace_width
            best_current = 0
            best_moment = 0
        
        # Create moment vs current data
        # Generate current points from 0 to P/V
        max_current = self.config.max_power / self.config.voltage
        currents = np.linspace(0, max_current, num_points)
        moments_vs_current = []
        
        # Calculate magnetic moment for the optimal trace width at each current
        for i in currents:
            moment = self.calculate_magnetic_moment(best_width, i)
            moments_vs_current.append(moment)
        
        # Convert widths to mm for plotting
        plot_widths = valid_widths * 1000
        
        return (
            self.analyze_result(best_width),
            (plot_widths.tolist(), valid_moments.tolist(), best_width * 1000, best_moment),
            (currents.tolist(), moments_vs_current, best_current, best_moment)
        )

    def analyze_result(self, trace_width: float) -> dict:
        """Analyze design results"""
        resistance = self.calculate_resistance(trace_width)
        current = self.calculate_current(resistance, trace_width)
        num_turns = self.calculate_max_turns(trace_width)
        
        # Calculate total wire length
        total_length = sum(self.calculate_turn_length(turn, trace_width) 
                        for turn in range(num_turns))
        total_length *= self.coil_layers
        
        # Calculate performance metrics
        power = current * self.config.voltage
        temp_rise = self.calculate_temperature_rise(power)
        moment = self.calculate_magnetic_moment(trace_width, current)
        
        # Current density in A/m²
        current_density = current / (trace_width * self.copper_thickness)
        
        # Calculate time constant metrics
        inductance = self.calculate_inductance(trace_width)
        time_constant = self.calculate_time_constant(trace_width)
        time_to_99_percent = self.calculate_time_to_percentage(trace_width, 0.99)
        
        return {
            "dimensions": {
                "inner": {
                    "length": round(self.config.inner_length * 1000, 1),    # mm
                    "width": round(self.config.inner_width * 1000, 1)       # mm
                },
                "outer": {
                    "length": round(self.config.outer_length * 1000, 1),    # mm
                    "width": round(self.config.outer_width * 1000, 1)       # mm
                }
            },
            "traces": {
                "width": round(trace_width * 1000, 3),                      # mm      
                "spacing": round(self.config.min_trace_spacing * 1000, 3),  # mm
                "turns_per_layer": num_turns,                               # [dimensionless]
                "total_layers": self.config.num_layers,                     # [dimensionless]
                "total_length": round(total_length, 1)                      # m
            },
            "electrical": {
                "resistance": round(resistance, 2),                         # Ω
                "voltage": round(self.config.voltage, 2),                   # V
                "current": round(current, 2),                               # A
                "power": round(current * self.config.voltage, 2),           # W
                "current_density": round(current_density/1e6, 2)            # A/mm^2
            },
            "thermal": {
                "space": {
                    "ambient": 0.0,                                         # ºC
                    "temperature_rise": round(temp_rise, 2),                # ºC
                    "final_temperature": round(temp_rise, 2)                # ºC
                }
            },
            "dynamics": {
                "inductance": round(inductance * 1000, 3),                  # μH
                "time_constant": round(time_constant * 1000, 2),            # ms
                "time_to_99_percent": round(time_to_99_percent * 1000, 2),  # ms
                "max_moment_99_percent": round(moment * 0.99, 4)             # A·m²
            },
            "performance": {
                "magnetic_moment": round(moment, 4)                         # A·m²
            },
        }

def main():
    # Load configuration
    with open('constraints.json', 'r') as f:
        config_data = json.load(f)
    
    # Create config object
    config = PCBConfig.from_json(config_data)
    
    # Create designer and optimize
    designer = MagnetorquerDesigner(config)
    result, width_data, current_data = designer.optimize(num_points=5000)
    
    # Unpack plot data
    widths, moments_width, best_width, best_moment = width_data
    currents, moments_current, best_current, best_moment = current_data
    
    # First plot: Moment vs Width
    fig1 = go.Figure()
    
    fig1.add_trace(
        go.Scatter(
            x=widths,
            y=moments_width,
            mode='lines',
            name='Moment vs Width',
            line=dict(color='blue', width=2)
        )
    )
    
    # Add optimal point
    fig1.add_trace(
        go.Scatter(
            x=[best_width],
            y=[best_moment],
            mode='markers',
            name='Optimal Point',
            marker=dict(color='red', size=10, symbol='star')
        )
    )
    
    # Update layout for first plot
    fig1.update_layout(
        title='Magnetic Moment vs Trace Width',
        xaxis_title='Trace Width (mm)',
        yaxis_title='Magnetic Moment (A·m²)',
        hovermode='x',
        template='plotly_white',
        showlegend=True
    )
    
    fig1.add_annotation(
        x=best_width,
        y=best_moment,
        text=f'Optimal:\n{best_width:.2f}mm\n{best_moment:.4f}A·m²',
        showarrow=True,
        arrowhead=1,
        yshift=10
    )
    
    # Second plot: Moment vs Current
    fig2 = go.Figure()
    
    fig2.add_trace(
        go.Scatter(
            x=currents,
            y=moments_current,
            mode='lines',
            name='Moment vs Current',
            line=dict(color='green', width=2)
        )
    )
    
    # Add operating point
    fig2.add_trace(
        go.Scatter(
            x=[best_current],
            y=[best_moment],
            mode='markers',
            name='Operating Point',
            marker=dict(color='red', size=10, symbol='star')
        )
    )
    
    # Add V/R and P/V lines
    optimal_resistance = result['electrical']['resistance']
    v_over_r = config.voltage / optimal_resistance
    p_over_v = config.max_power / config.voltage
    
    # Add vertical lines with annotations
    fig2.add_vline(
        x=v_over_r, 
        line_dash="dash", 
        line_color="gray",
        annotation_text=f"V/R = {v_over_r:.2f}A"
    )
    
    fig2.add_vline(
        x=p_over_v, 
        line_dash="dash", 
        line_color="gray",
        annotation_text=f"P/V = {p_over_v:.2f}A"
    )
    
    # Update layout for second plot
    fig2.update_layout(
        title='Magnetic Moment vs Current',
        xaxis_title='Current (A)',
        yaxis_title='Magnetic Moment (A·m²)',
        hovermode='x',
        template='plotly_white',
        showlegend=True
    )
    
    fig2.add_annotation(
        x=best_current,
        y=best_moment,
        text=f'Operating Point:\n{best_current:.2f}A\n{best_moment:.4f}A·m²',
        showarrow=True,
        arrowhead=1,
        yshift=10
    )
    
    # Save and open both plots
    filename1 = 'magnetic_moment_vs_width.html'
    filename2 = 'magnetic_moment_vs_current.html'
    
    fig1.write_html(filename1)
    fig2.write_html(filename2)
    
    # Open both plots in browser
    webbrowser.open('file://' + os.path.abspath(filename1))
    webbrowser.open('file://' + os.path.abspath(filename2))
    
    # Print results
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()