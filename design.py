import numpy as np
from scipy.optimize import minimize, fsolve
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
        """Calculate length of a specific turn including connections beyond outer bounds"""
        # Calculate offset from edge for this turn
        offset = turn_number * (trace_width + self.min_trace_spacing)
        
        # Current rectangle dimensions
        current_length = self.outer_length - 2 * offset
        current_width = self.outer_width - 2 * offset
        
        # Main rectangular path
        perimeter = 2 * (current_length + current_width)
        
        # Add connection to next turn if not the last turn
        # Connections can extend beyond outer bounds, so we don't need to constrain them
        if turn_number < self.calculate_max_turns(trace_width) - 1:
            # Connection follows the spiral pattern with more freedom
            connection_horizontal = trace_width + self.min_trace_spacing
            connection_vertical = trace_width + self.min_trace_spacing
            connection_length = connection_horizontal + connection_vertical
        else:
            # For last turn, just need room for output connection
            connection_length = trace_width + self.min_trace_spacing
        
        return perimeter + connection_length

    def calculate_max_turns(self, trace_width):
        """Calculate maximum turns ensuring inner clearance for connections"""
        if trace_width <= 0:
            return 0
            
        # Minimum clearance from inner bounds for connections
        # Need space for:
        # 1. The connection trace itself
        # 2. Minimum spacing requirement
        # 3. Additional safety margin
        min_inner_clearance = 2 * (trace_width + 2 * self.min_trace_spacing)
        
        # Calculate available space from outer edge to inner edge
        # Now we need to subtract the clearance from the available space
        effective_inner_length = self.inner_length + 2 * min_inner_clearance
        effective_inner_width = self.inner_width + 2 * min_inner_clearance
        
        available_height = (self.outer_length - effective_inner_length) / 2
        available_width = (self.outer_width - effective_inner_width) / 2
        
        if available_height <= 0 or available_width <= 0:
            return 0
        
        # Each turn needs space for:
        # 1. Trace width
        # 2. Spacing to next turn
        turn_pitch = trace_width + self.min_trace_spacing
        
        # Calculate turns that can fit in the smaller dimension
        max_turns_height = int(available_height / turn_pitch)
        max_turns_width = int(available_width / turn_pitch)
        
        # Use the more constraining dimension
        max_turns = min(max_turns_height, max_turns_width)
        
        return max(1, max_turns)

    def calculate_area(self, turn_number, trace_width):
        """Calculate area enclosed by a specific turn accounting for inner clearance"""
        # Calculate minimum clearance requirement
        min_inner_clearance = 2 * (trace_width + 2 * self.min_trace_spacing)
        
        # Base offset from outer edge
        offset = turn_number * (trace_width + self.min_trace_spacing)
        
        # Current rectangle dimensions
        length = self.outer_length - 2 * offset
        width = self.outer_width - 2 * offset
        
        # Verify we're not too close to inner cutout
        effective_inner_length = self.inner_length + 2 * min_inner_clearance
        effective_inner_width = self.inner_width + 2 * min_inner_clearance
        
        # If this turn would be too close to inner cutout, return 0 area
        if length < effective_inner_length or width < effective_inner_width:
            return 0
        
        # Area of main rectangular path
        return length * width

    def is_design_valid(self, trace_width, num_turns):
        """Validate that design maintains proper clearance from inner cutout"""
        # Calculate minimum required clearance
        min_inner_clearance = 2 * (trace_width + 2 * self.min_trace_spacing)
        
        # Calculate the innermost turn's position
        final_offset = (num_turns - 1) * (trace_width + self.min_trace_spacing)
        
        # Calculate effective dimensions of innermost turn
        min_length = self.outer_length - 2 * final_offset
        min_width = self.outer_width - 2 * final_offset
        
        # Check clearance from inner cutout
        length_clearance = (min_length - self.inner_length) / 2
        width_clearance = (min_width - self.inner_width) / 2
        
        # Both clearances must be greater than minimum required
        if length_clearance < min_inner_clearance:
            return False
        if width_clearance < min_inner_clearance:
            return False
        
        return True

    def calculate_resistance(self, num_turns, trace_width):
        """Calculate total resistance of the rectangular coil at room temperature"""
        if num_turns <= 0 or trace_width <= 0:
            return np.inf
            
        # Sum up length of all turns
        total_wire_length = sum(self.calculate_turn_length(turn, trace_width) 
                            for turn in range(num_turns))
        
        total_wire_length *= self.coil_layers
        
        # Use 4.5 mils for copper thickness (more accurate than oz calculation)
        copper_thickness = 4.5 * 25.4e-6  # convert 4.5 mils to meters
        wire_cross_section = copper_thickness * trace_width
        
        if wire_cross_section <= 0:
            return np.inf
            
        # Calculate base resistance at room temperature (20°C)
        room_temp_resistance = self.copper_resistivity * total_wire_length / wire_cross_section
        
        # Only apply temperature compensation if we're not at room temp
        if self.operating_temp != 20:  # if operating temp is different from room temp
            temp_factor = 1 + self.temperature_coefficient * (self.operating_temp - 20)
            return room_temp_resistance * temp_factor
        
        return room_temp_resistance

    def calculate_magnetic_moment(self, num_turns, current):
        """Calculate magnetic moment of rectangular coil"""
        if num_turns <= 0 or current <= 0:
            return 0
        
        # Sum up the areas of all turns
        total_area = sum(self.calculate_area(turn, self.max_trace_width) 
                        for turn in range(num_turns))
        
        return total_area * current * self.coil_layers

    def calculate_temperature_rise_ground_test(self, current, trace_width, length_per_turn, num_turns):
        """Calculate temperature rise for lab testing - radiation only, starting from room temp"""
        # Constants
        stefan_boltzmann = 5.67e-8  # W/(m²·K⁴)
        emissivity = 0.9  # Typical for PCB materials
        T_room = 293.15  # 20°C in Kelvin
        
        # Power dissipated
        resistance = self.calculate_resistance(num_turns, trace_width)
        power_dissipated = current**2 * resistance
        
        # Surface area calculation
        board_area = self.outer_length * self.outer_width
        radiating_area = 2 * board_area  # Both sides can radiate
        
        def heat_balance(T):
            # P = εσA(T⁴ - T_room⁴)
            radiation_power = emissivity * stefan_boltzmann * radiating_area * (T**4 - T_room**4)
            return radiation_power - power_dissipated
        
        # Solve for equilibrium temperature
        from scipy.optimize import fsolve
        T_final = fsolve(heat_balance, T_room + 5)[0]  # Start guess at room temp + 5K
    
        return T_final - T_room  # Return temperature rise in Kelvin

    def calculate_temperature_rise_space(self, current, trace_width, length_per_turn, num_turns):
        """Calculate temperature rise for space operation"""
        stefan_boltzmann = 5.67e-8
        emissivity = 0.9
        T_space = 273.15  # 0ºC in Kelvin for satellite ambient
        
        resistance = self.calculate_resistance(num_turns, trace_width)
        power_dissipated = current**2 * resistance
        
        board_area = self.outer_length * self.outer_width
        radiating_area = 2 * board_area
        
        def heat_balance(T):
            radiation_power = emissivity * stefan_boltzmann * radiating_area * (T**4 - T_space**4)
            return radiation_power - power_dissipated
        
        T_final = fsolve(heat_balance, T_space + 5)[0]
        
        return T_final - T_space

    def is_thermal_safe(self, current, trace_width, length_per_turn, num_turns):
        """Check both ground testing and space operation thermal limits"""
        # Ground test temperature rise
        temp_rise_ground = self.calculate_temperature_rise_ground_test(
            current, trace_width, length_per_turn, num_turns)
        final_temp_ground = 20 + temp_rise_ground  # Starting from 20°C room temp
        
        # Space operation temperature rise
        temp_rise_space = self.calculate_temperature_rise_space(
            current, trace_width, length_per_turn, num_turns)
        final_temp_space = 0 + temp_rise_space  # Starting from 0°C satellite ambient
        
        # Check both conditions
        return (final_temp_ground <= self.operating_temp and 
                final_temp_space <= self.operating_temp)

    def calculate_inductance(self, num_turns, trace_width):
        """Calculate approximate inductance of the coil"""
        # Using Wheeler's formula for rectangular coil inductance
        # L = K1 * μ0 * N² * a * ln(K2/ρ)
        # where:
        # K1, K2 are geometry-dependent constants
        # a is mean radius of coil
        # ρ is fill ratio (wire diameter / coil pitch)
        
        if num_turns <= 0:
            return 0
        
        # Mean dimensions
        mean_length = (self.outer_length + self.inner_length) / 2
        mean_width = (self.outer_width + self.inner_width) / 2
        
        # Geometric mean radius
        a = np.sqrt(mean_length * mean_width) / (2 * np.pi)
        
        # Fill ratio (trace width / center-to-center spacing)
        pitch = trace_width + self.min_trace_spacing
        fill_ratio = trace_width / pitch
        
        # Constants for rectangular coil
        K1 = 2.34  # Empirical constant for rectangular coils
        K2 = 2.75  # Empirical constant for rectangular coils
        
        # Calculate inductance (in Henries)
        L = K1 * self.mu_0 * (num_turns * self.coil_layers)**2 * a * np.log(K2/fill_ratio)
        
        return L

    def calculate_current(self, resistance):
        """Calculate current given resistance and voltage constraints"""
        if resistance <= 0:
            return 0
        return min(self.v_dd / resistance, self.max_current)

    def objective_function(self, x):
        """Modified objective function with relaxed outer bounds"""
        trace_width = x[0]
        
        if trace_width < self.min_trace_width or trace_width > self.max_trace_width:
            return 0
            
        max_turns = self.calculate_max_turns(trace_width)
        
        # Validate design doesn't intrude into inner cutout
        if not self.is_design_valid(trace_width, max_turns):
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
        inductance = self.calculate_inductance(max_turns, trace_width)
        
        mid_turn_length = self.calculate_turn_length(max_turns//2, trace_width)
        
        # Calculate both thermal scenarios
        temp_rise_ground = self.calculate_temperature_rise_ground_test(
            current, trace_width, mid_turn_length, max_turns)
        temp_rise_space = self.calculate_temperature_rise_space(
            current, trace_width, mid_turn_length, max_turns)
        
        final_temp_ground = 20 + temp_rise_ground
        final_temp_space = 0 + temp_rise_space
        
        magnetic_moment = self.calculate_magnetic_moment(max_turns, current)
        
        # Calculate total wire length
        total_length = sum(self.calculate_turn_length(turn, trace_width) 
                        for turn in range(max_turns))
        total_length *= self.coil_layers
        
        return {
            'inner_length': self.inner_length * 1000,                                                           # mm
            'inner_width': self.inner_width * 1000,                                                             # mm
            'outer_length': self.outer_length * 1000,                                                           # mm
            'outer_width': self.outer_width * 1000,                                                             # mm
            'trace_width': trace_width * 1000,                                                                  # mm
            'trace_spacing': self.min_trace_spacing * 1000,                                                     # mm
            'num_turns': max_turns,                                                                             # dimensionless
            'resistance': resistance,                                                                           # ohms
            'current': current,                                                                                 # A
            'voltage': self.v_dd,                                                                               # V
            'magnetic_moment': magnetic_moment,                                                                 # Am^2
            'power': current * self.v_dd,                                                                       # W
            'temperature_rise_ground': temp_rise_ground,                                                        # ºC
            'final_temp_ground': final_temp_ground,                                                             # ºC
            'temperature_rise_space': temp_rise_space,                                                          # ºC
            'final_temp_space': final_temp_space,                                                               # ºC
            'wire_length': total_length,                                                                        # m
            'current_density': current / (trace_width * self.copper_thickness) if trace_width > 0 else 0,       # A/mm^2
            'inductance': inductance,                                                                           # H * 10^-6              
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
            "total_length": round(result['wire_length'], 1),
        },
        "electrical": {
            "resistance": round(result['resistance'], 2),
            "voltage": round(result['voltage'], 1),
            "current": round(result['current'], 3),
            "power": round(result['power'], 2),
            "current_density": round(result['current_density']/1e6, 2),
            "inductance": round(result['inductance']*1e6, 2),
        },
        "thermal": {
            "ground_test": {
                "ambient": 20.0,
                "temperature_rise": round(result['temperature_rise_ground'], 1),
                "final_temperature": round(result['final_temp_ground'], 1)
            },
            "space": {
                "ambient": 0.0,
                "temperature_rise": round(result['temperature_rise_space'], 1),
                "final_temperature": round(result['final_temp_space'], 1)
            }
        },
        "performance": {
            "magnetic_moment": round(result['magnetic_moment'], 4)
        }
    }
    
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()