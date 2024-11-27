import numpy as np
from dataclasses import dataclass
from scipy.optimize import minimize, fsolve
from typing import Dict, Any
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
import webbrowser
import os
import json
import sys


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
        """Calculate inductance of PCB coil using Wheeler's formula for rectangular coils
        
        Args:
            trace_width: Width of the PCB trace in meters
        Returns:
            Inductance in Henries
        """
        num_turns = self.calculate_max_turns(trace_width)
        if num_turns <= 0:
            return 0
            
        # Calculate average diameter 
        spacing = trace_width + self.config.min_trace_spacing
        avg_length = self.config.outer_length - spacing * num_turns
        avg_width = self.config.outer_width - spacing * num_turns
        avg_diameter = (avg_length + avg_width) / 2
        
        # Wheeler's formula for rectangular coils
        inductance = (31.33 * self.config.vacuum_permeability * 
                    num_turns**2 * avg_diameter / 8)
                    
        # Account for multiple layers
        inductance *= self.coil_layers
        
        return inductance

    def calculate_time_constant(self, trace_width: float) -> float:
        """Calculate the RL time constant (τ = L/R)
        
        Args:
            trace_width: Width of the PCB trace in meters
        Returns:
            Time constant in seconds
        """
        inductance = self.calculate_inductance(trace_width)
        resistance = self.calculate_resistance(trace_width)
        
        if resistance <= 0:
            return 0
            
        tau = inductance / resistance
        return tau
    

    def calculate_time_to_percentage(self, trace_width: float, target_percentage: float) -> float:
        """Calculate time to reach a target percentage of final value"""
        tau = self.calculate_time_constant(trace_width)
        # Using the formula: percentage = 1 - e^(-t/tau)
        # Solving for t: t = -tau * ln(1 - percentage)
        return -tau * np.log(1 - target_percentage)
    
    def calculate_power_efficiency(self, moment: float, current: float, resistance: float) -> float:
        """Calculate power efficiency as magnetic moment per watt of input power
        
        Args:
            moment: Magnetic moment in A·m²
            current: Current in amperes
            resistance: Resistance in ohms
            
        Returns:
            Power efficiency in A·m²/W
        """
        # Calculate power using P = I * V since we're using a constant voltage source
        power = current * self.config.voltage
        
        if power <= 0:
            return 0
            
        return moment / power  # Units: (A·m²) / W = A·m²/W
        
    def calculate_thermal_efficiency(self, current, moment, power, temp_rise) -> float:
        """Calculate thermal efficiency as moment per degree C rise"""
        power = current * self.config.voltage
        temp_rise = self.calculate_temperature_rise(power)
        
        if temp_rise <= 0:
            return 0
            
        return moment / temp_rise

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

    def optimize(self, num_points: int = 5000) -> tuple[dict, list, list, list, list]:
        widths_array = np.logspace(
            np.log10(self.config.min_trace_width),
            np.log10(self.config.max_trace_width),
            num_points
        )
        
        moments_array = np.zeros_like(widths_array)
        thermal_eff_array = np.zeros_like(widths_array)
        power_eff_array = np.zeros_like(widths_array)
        tau_array = np.zeros_like(widths_array)
        valid_designs = np.zeros_like(widths_array, dtype=bool)
        
        num_turns_array = np.zeros_like(widths_array)
        resistance_array = np.zeros_like(widths_array)
        inductance_array = np.zeros_like(widths_array)
        current_array = np.zeros_like(widths_array)
        
        debug_interval = num_points // 10
        for i, width in enumerate(widths_array):
            if self.check_constraints(width):
                resistance = self.calculate_resistance(width)
                current = self.calculate_current(resistance, width)
                moment = self.calculate_magnetic_moment(width, current)
                power = current * self.config.voltage  # Use V*I for power
                temp_rise = self.calculate_temperature_rise(power)
                inductance = self.calculate_inductance(width)
                tau = self.calculate_time_constant(width)
                num_turns = self.calculate_max_turns(width)
                
                moments_array[i] = moment
                thermal_eff_array[i] = self.calculate_thermal_efficiency(current, moment, power, temp_rise)
                power_eff_array[i] = self.calculate_power_efficiency(moment, current, resistance)
                tau_array[i] = tau * 1000
                valid_designs[i] = True
                
                num_turns_array[i] = num_turns
                resistance_array[i] = resistance
                inductance_array[i] = inductance
                current_array[i] = current
        
        print("\nOverall Trends:")
        valid_mask = valid_designs & ~np.isnan(moments_array)
        print(f"Number of valid designs: {np.sum(valid_mask)}")
        print(f"Number of turns range: {int(np.min(num_turns_array[valid_mask]))} to {int(np.max(num_turns_array[valid_mask]))}")
        print(f"Resistance range: {np.min(resistance_array[valid_mask]):.2f} to {np.max(resistance_array[valid_mask]):.2f} Ω")
        print(f"Inductance range: {np.min(inductance_array[valid_mask])*1000:.2f} to {np.max(inductance_array[valid_mask])*1000:.2f} μH")
        print(f"Current range: {np.min(current_array[valid_mask]):.3f} to {np.max(current_array[valid_mask]):.3f} A")
        print(f"Moment range: {np.min(moments_array[valid_mask]):.6f} to {np.max(moments_array[valid_mask]):.6f} A·m²")
        print(f"Time constant range: {np.min(tau_array[valid_mask]):.2f} to {np.max(tau_array[valid_mask]):.2f} ms")

        valid_mask = valid_designs & ~np.isnan(moments_array)
        valid_widths = widths_array[valid_mask]
        valid_moments = moments_array[valid_mask]
        valid_thermal_eff = thermal_eff_array[valid_mask]
        valid_power_eff = power_eff_array[valid_mask]
        valid_tau = tau_array[valid_mask]

        if len(valid_moments) > 0:
            moment_idx = np.argmax(valid_moments)
            best_moment_width = valid_widths[moment_idx]
            best_moment = valid_moments[moment_idx]
            
            thermal_idx = np.argmax(valid_thermal_eff)
            best_thermal_width = valid_widths[thermal_idx]
            best_thermal_eff = valid_thermal_eff[thermal_idx]
            
            power_idx = np.argmax(valid_power_eff)
            best_power_width = valid_widths[power_idx]
            best_power_eff = valid_power_eff[power_idx]
            
            tau_idx = np.argmin(valid_tau)
            best_tau_width = valid_widths[tau_idx]
            best_tau = valid_tau[tau_idx]
            
            print("\nOptimal Points:")
            print(f"Best moment: {best_moment:.6f} A·m² at width {best_moment_width*1000:.3f} mm")
            print(f"Best thermal efficiency: {best_thermal_eff:.6f} A·m²/°C at width {best_thermal_width*1000:.3f} mm")
            print(f"Best power efficiency: {best_power_eff:.6f} A·m²/W at width {best_power_width*1000:.3f} mm")
            print(f"Best time constant: {best_tau:.2f} ms at width {best_tau_width*1000:.3f} mm")
        else:
            best_moment_width = best_thermal_width = best_power_width = best_tau_width = self.config.min_trace_width
            best_moment = best_thermal_eff = best_power_eff = best_tau = 0
        
        plot_widths = valid_widths * 1000
        
        moment_data = (plot_widths.tolist(), valid_moments.tolist(), best_moment_width * 1000, best_moment)
        thermal_data = (plot_widths.tolist(), valid_thermal_eff.tolist(), best_thermal_width * 1000, best_thermal_eff)
        power_data = (plot_widths.tolist(), valid_power_eff.tolist(), best_power_width * 1000, best_power_eff)
        tau_data = (plot_widths.tolist(), valid_tau.tolist(), best_tau_width * 1000, best_tau)
        
        return (
            self.analyze_result(best_moment_width),
            moment_data,
            thermal_data,
            power_data,
            tau_data
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
    
def ensure_directories():
    """Create necessary output directories if they don't exist"""
    directories = ['output', 'designs', 'plots']
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")
    return directories

def get_base_filename(constraints_file: str) -> str:
    """Extract base filename from constraints file path"""
    # Get just the filename without path
    filename = os.path.basename(constraints_file)
    # Remove '-constraints.json' suffix if present
    if filename.endswith('-constraints.json'):
        return filename[:-17]  # Remove '-constraints.json'
    # If doesn't end with -constraints.json, just remove .json
    return os.path.splitext(filename)[0]

def main():
    # Check if a constraints file was provided
    if len(sys.argv) < 2:
        print("Usage: python script.py <path_to_constraints_file>")
        sys.exit(1)
        
    constraints_file = sys.argv[1]
    
    try:
        # Create output directories
        ensure_directories()
        
        # Get base name for output files
        base_filename = get_base_filename(constraints_file)
        
        # Load configuration
        with open(constraints_file, 'r') as f:
            config_data = json.load(f)
        
        # Create config object
        config = PCBConfig.from_json(config_data)
        
        # Create designer and optimize
        designer = MagnetorquerDesigner(config)
        result, moment_data, thermal_data, power_data, tau_data = designer.optimize(num_points=5000)
        
        # Unpack plot data
        widths, moments, best_moment_width, best_moment = moment_data
        _, thermal_eff, best_thermal_width, best_thermal = thermal_data
        _, power_eff, best_power_width, best_power = power_data
        _, taus, best_tau_width, best_tau = tau_data
        
        # Create figure with subplots (1x2 grid)
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=(
                'Magnetic Moment vs Trace Width', 
                # 'Thermal Efficiency (Am²/°C) vs Trace Width',
                'Power Efficiency (Am²/W) vs Trace Width',
                # 'Time Constant τ (ms) vs Trace Width'
            ),
            horizontal_spacing=0.15,
            vertical_spacing=0.15
        )

        # Plot 1: Moment vs Width (top left)
        fig.add_trace(
            go.Scatter(
                x=widths,
                y=moments,
                mode='lines',
                name='Magnetic Moment',
                line=dict(color='rgb(0, 123, 255)', width=2)
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=[best_moment_width],
                y=[best_moment],
                mode='markers',
                name='Maximum Moment',
                marker=dict(
                    color='rgb(220, 53, 69)',
                    size=12,
                    symbol='star-diamond',
                    line=dict(color='rgb(150, 20, 30)', width=2)
                )
            ),
            row=1, col=1
        )

        # # Plot 2: Thermal Efficiency (top right)
        # fig.add_trace(
        #     go.Scatter(
        #         x=widths,
        #         y=thermal_eff,
        #         mode='lines',
        #         name='Thermal Efficiency',
        #         line=dict(color='rgb(40, 167, 69)', width=2)
        #     ),
        #     row=1, col=2
        # )
        
        # fig.add_trace(
        #     go.Scatter(
        #         x=[best_thermal_width],
        #         y=[best_thermal],
        #         mode='markers',
        #         name='Best Thermal Efficiency',
        #         marker=dict(
        #             color='rgb(25, 135, 84)',
        #             size=12,
        #             symbol='star-diamond',
        #             line=dict(color='rgb(15, 95, 55)', width=2)
        #         )
        #     ),
        #     row=1, col=2
        # )

        # Plot 3: Power Efficiency (bottom left)
        fig.add_trace(
            go.Scatter(
                x=widths,
                y=power_eff,
                mode='lines',
                name='Power Efficiency',
                line=dict(color='rgb(111, 66, 193)', width=2)
            ),
            row=1, col=2
        )
        
        fig.add_trace(
            go.Scatter(
                x=[best_power_width],
                y=[best_power],
                mode='markers',
                name='Best Power Efficiency',
                marker=dict(
                    color='rgb(128, 0, 128)',
                    size=12,
                    symbol='star-diamond',
                    line=dict(color='rgb(76, 0, 76)', width=2)
                )
            ),
            row=1, col=2
        )

        # # Plot 4: Time Constant (bottom right)
        # fig.add_trace(
        #     go.Scatter(
        #         x=widths,
        #         y=taus,
        #         mode='lines',
        #         name='Time Constant',
        #         line=dict(color='rgb(255, 193, 7)', width=2)
        #     ),
        #     row=2, col=2
        # )
        
        # fig.add_trace(
        #     go.Scatter(
        #         x=[best_tau_width],
        #         y=[best_tau],
        #         mode='markers',
        #         name='Minimum Time Constant',
        #         marker=dict(
        #             color='rgb(253, 126, 20)',
        #             size=12,
        #             symbol='star-diamond',
        #             line=dict(color='rgb(210, 100, 0)', width=2)
        #         )
        #     ),
        #     row=2, col=2
        # )

        # Update axes labels and properties
        for row in [1, 2]:
            for col in [1, 2]:
                fig.update_xaxes(
                    title='Trace Width (mm)',
                    gridcolor='lightgray',
                    showgrid=True,
                    row=row,
                    col=col
                )

        # Update y-axis titles
        fig.update_yaxes(title='Magnetic Moment (A·m²)', row=1, col=1)
        # fig.update_yaxes(title='Moment/°C (A·m²/°C)', row=1, col=2)
        fig.update_yaxes(title='Moment/Power (A·m²/W)', row=2, col=1)
        # fig.update_yaxes(title='Time Constant (ms)', row=2, col=2)

        # Update overall layout
        fig.update_layout(
            height=500,
            width=1400,
            showlegend=True,
            template='plotly_white',
            hovermode='x unified',
            title=f"{(lambda x: " ".join(word.capitalize() for word in x.split("-")))(base_filename)} Design Analysis Plots"
        )

        # Save and open plot
        filename = f'plots/{base_filename}-design-analysis.html'
        fig.write_html(filename)
        webbrowser.open('file://' + os.path.abspath(filename))
        pio.write_image(fig, f'plots/{base_filename}-design-analysis.png')
        
        # Save JSON file
        json_filename = f'designs/{base_filename}-design.json'
        with open(json_filename, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"JSON saved to: {json_filename}")

    except FileNotFoundError:
        print(f"Error: Constraints file '{constraints_file}' not found")
    except json.JSONDecodeError:
        print(f"Error: '{constraints_file}' contains invalid JSON")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()