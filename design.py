import numpy as np
from scipy.optimize import minimize
import json

class MagnetorquerOptimizer:
    def __init__(self, config_file):
        # Load configuration
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # Physical constants
        constants = config.get('physical_constants', {})
        self.mu_0 = constants.get('vacuum_permeability', 4 * np.pi * 1e-7)  # H/m
        self.copper_resistivity = constants.get('copper_resistivity', 1.68e-8)  # Ohm·m at 20°C
        self.temperature_coefficient = constants.get('temperature_coefficient', 0.00393)  # per °C
        self.oz_to_m = constants.get('oz_to_m', 0.0347e-3)  # Convert oz copper to meters thickness
        
        # Thermal properties
        thermal = config.get('thermal_properties', {})
        self.thermal_conductivity_copper = thermal.get('thermal_conductivity_copper', 385)  # W/(m·K)
        self.thermal_conductivity_fr4 = thermal.get('thermal_conductivity_fr4', 0.3)  # W/(m·K)
        self.fr4_thickness = thermal.get('fr4_thickness', 1.6e-3)  # m
        self.surface_area_multiplier = thermal.get('surface_area_multiplier', 2)  # both sides
        self.convection_coefficient = thermal.get('convection_coefficient', 10)  # W/(m²·K)
        
        # Design constraints
        design = config.get('design_constraints', {})
        self.num_layers = design.get('num_layers', 6)
        self.coil_layers = design.get('num_layers', 6) - 1 # need one layer to connect to h-bridge
        self.copper_weight = design.get('copper_weight', 2)  # oz
        self.copper_thickness = self.copper_weight * self.oz_to_m
        self.max_power = design.get('max_power', 4)  # Watts
        self.v_dd = design.get('voltage', 8.2)  # Volts
        self.inner_length = design.get('inner_length', 0.02)  # m
        self.inner_width = design.get('inner_width', 0.02)  # m
        self.outer_length = design.get('outer_length', 0.1)  # m
        self.outer_width = design.get('outer_width', 0.1)  # m
        self.operating_temp = design.get('operating_temp', 85)  # °C
        self.ambient_temp = design.get('ambient_temp', 20)  # °C
        
        # PCB manufacturing constraints
        manufacturing = config.get('manufacturing_constraints', {})
        self.min_trace_width = manufacturing.get('min_trace_width', 0.45e-3)  # Updated to 0.45mm
        self.max_trace_width = manufacturing.get('max_trace_width', 0.45e-3)  # Set equal to get consistent width
        self.min_trace_spacing = manufacturing.get('min_trace_spacing', 0.1e-3)  # m
        
        # Calculate derived constraints
        self.max_current = self.max_power / self.v_dd
        self.current_density_limit = constants.get('current_density_limit', 35e6)  # A/m²

    def calculate_turn_length(self, turn_number, trace_width):
        """Calculate length of a specific turn starting from outer edge"""
        offset = turn_number * (trace_width + self.min_trace_spacing)
        current_length = self.outer_length - 2 * offset
        current_width = self.outer_width - 2 * offset
        
        # Account for spiral progression
        long_side1 = current_length
        short_side1 = current_width
        long_side2 = current_length - (trace_width + self.min_trace_spacing)
        short_side2 = current_width - (trace_width + self.min_trace_spacing)
        
        return long_side1 + short_side1 + long_side2 + short_side2

    def calculate_area(self, turn_number, trace_width):
        """Calculate area enclosed by a specific turn starting from outer edge"""
        offset = turn_number * (trace_width + self.min_trace_spacing)
        length = self.outer_length - 2 * offset
        width = self.outer_width - 2 * offset
        return length * width

    def calculate_max_turns(self, trace_width):
        """Calculate maximum number of turns possible between outer and inner edges"""
        if trace_width <= 0:
            return 0
            
        # Calculate available space in both dimensions
        available_height = (self.outer_length - self.inner_length) / 2
        available_width = (self.outer_width - self.inner_width) / 2
        
        if available_height <= 0 or available_width <= 0:
            return 0
            
        # Calculate turns that can fit in the smaller dimension
        # Account for trace width and spacing on both sides
        max_turns = min(
            int(available_height / (trace_width + 2 * self.min_trace_spacing)),
            int(available_width / (trace_width + 2 * self.min_trace_spacing))
        )
        
        return max(1, max_turns)

    def calculate_resistance(self, num_turns, trace_width):
        """Calculate total resistance of the rectangular coil"""
        if num_turns <= 0 or trace_width <= 0:
            return np.inf
            
        # Sum up length of all turns
        total_wire_length = sum(self.calculate_turn_length(turn, trace_width) 
                              for turn in range(num_turns))
        
        total_wire_length *= self.coil_layers
        wire_cross_section = self.copper_thickness * trace_width
        
        if wire_cross_section <= 0:
            return np.inf
            
        base_resistance = self.copper_resistivity * total_wire_length / wire_cross_section
        temp_factor = 1 + self.temperature_coefficient * (self.operating_temp - self.ambient_temp)
        return base_resistance * temp_factor

    def calculate_magnetic_moment(self, num_turns, current):
        """Calculate magnetic moment of rectangular coil"""
        if num_turns <= 0 or current <= 0:
            return 0
        
        # Sum up the areas of all turns
        total_area = sum(self.calculate_area(turn, self.max_trace_width) 
                        for turn in range(num_turns))
        
        return total_area * current * self.coil_layers

    def calculate_temperature_rise(self, current, trace_width, length_per_turn, num_turns):
        """Calculate temperature rise with improved thermal model"""
        if current <= 0 or trace_width <= 0:
            return 0
            
        resistance = self.calculate_resistance(num_turns, trace_width)
        power_dissipated = current**2 * resistance
        trace_length = length_per_turn * num_turns * self.coil_layers
        surface_area = trace_length * trace_width * self.surface_area_multiplier
        
        R_conduction = self.fr4_thickness / (self.thermal_conductivity_fr4 * surface_area)
        R_convection = 1 / (self.convection_coefficient * surface_area)
        R_total = (R_conduction * R_convection) / (R_conduction + R_convection)
        
        return power_dissipated * R_total

    def is_thermal_safe(self, current, trace_width, length_per_turn, num_turns):
        """Check if design meets thermal constraints"""
        temp_rise = self.calculate_temperature_rise(current, trace_width, length_per_turn, num_turns)
        final_temp = self.ambient_temp + temp_rise
        return final_temp <= self.operating_temp

    def calculate_current(self, resistance):
        """Calculate current given resistance and voltage constraints"""
        if resistance <= 0:
            return 0
        return min(self.v_dd / resistance, self.max_current)

    def objective_function(self, x):
        """Objective function for rectangular coil optimization"""
        trace_width = x[0]
        
        if trace_width < self.min_trace_width or trace_width > self.max_trace_width:
            return 0
            
        max_turns = self.calculate_max_turns(trace_width)
        
        if max_turns == 0:
            return 0
            
        resistance = self.calculate_resistance(max_turns, trace_width)
        current = self.calculate_current(resistance)
        
        # Use middle turn for thermal calculations
        mid_turn_length = self.calculate_turn_length(max_turns//2, trace_width)
        if not self.is_thermal_safe(current, trace_width, mid_turn_length, max_turns):
            return 0
            
        power = current * self.v_dd
        if power > self.max_power:
            return 0
            
        moment = self.calculate_magnetic_moment(max_turns, current)
        return -moment if moment > 0 else 0

    def optimize(self):
        """Run optimization for rectangular coil"""
        x0 = [self.min_trace_width]  # Start with minimum trace width
        bounds = [(self.min_trace_width, self.max_trace_width)]
        
        result = minimize(self.objective_function, x0,
                         method='SLSQP',
                         bounds=bounds)
        
        return self.analyze_result(result)

    def analyze_result(self, result):
        """Analyze optimization results"""
        trace_width = result.x[0]
        max_turns = self.calculate_max_turns(trace_width)
        resistance = self.calculate_resistance(max_turns, trace_width)
        current = self.calculate_current(resistance)
        
        mid_turn_length = self.calculate_turn_length(max_turns//2, trace_width)
        temp_rise = self.calculate_temperature_rise(current, trace_width, mid_turn_length, max_turns)
        final_temp = self.ambient_temp + temp_rise
        
        magnetic_moment = self.calculate_magnetic_moment(max_turns, current)
        
        # Calculate total wire length
        total_length = sum(self.calculate_turn_length(turn, trace_width) 
                         for turn in range(max_turns))
        total_length *= self.coil_layers
        
        return {
            'inner_length': self.inner_length * 1000,  # Convert to mm
            'inner_width': self.inner_width * 1000,
            'outer_length': self.outer_length * 1000,
            'outer_width': self.outer_width * 1000,
            'trace_width': trace_width * 1000,
            'trace_spacing': self.min_trace_spacing * 1000,
            'num_turns': max_turns,
            'resistance': resistance,
            'current': current,
            'voltage': self.v_dd,
            'magnetic_moment': magnetic_moment,
            'power': current * self.v_dd,
            'temperature_rise': temp_rise,
            'final_temperature': final_temp,
            'wire_length': total_length,
            'current_density': current / (trace_width * self.copper_thickness) if trace_width > 0 else 0
        }

def main():
    # Create optimizer instance with config file
    optimizer = MagnetorquerOptimizer('constraints.json')
    result = optimizer.optimize()
    
    output = {
        "dimensions": {
            "inner": {
                "length": round(result['inner_length'], 1),
                "width": round(result['inner_width'], 1)
            },
            "outer": {
                "length": round(result['outer_length'], 1),
                "width": round(result['outer_width'], 1)
            }
        },
        "traces": {
            "width": round(result['trace_width'], 3),
            "spacing": round(result['trace_spacing'], 3),
            "turns_per_layer": result['num_turns'],
            "total_layers": optimizer.num_layers,
            "total_length": round(result['wire_length'], 2)
        },
        "electrical": {
            "resistance": round(result['resistance'], 2),
            "voltage": round(result['voltage'], 1),
            "current": round(result['current'], 3),
            "current_density": round(result['current_density']/1e6, 2),
            "power": round(result['power'], 2)
        },
        "thermal": {
            "temperature_rise": round(result['temperature_rise'], 1),
            "final_temperature": round(result['final_temperature'], 1)
        },
        "performance": {
            "magnetic_moment": format(result['magnetic_moment'], '.2e')
        }
    }
    
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()