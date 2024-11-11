import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
import json
import os

def ensure_output_directory():
    """Create output directory if it doesn't exist"""
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    return output_dir

def format_design_info(data):
    """Format complete design information for display"""
    info = []
    
    # Dimensions
    info.append("Dimensions:")
    info.append(f"  Outer: {data['dimensions']['outer']['length']:.1f}mm × {data['dimensions']['outer']['width']:.1f}mm")
    info.append(f"  Inner: {data['dimensions']['inner']['length']:.1f}mm × {data['dimensions']['inner']['width']:.1f}mm")
    
    # Traces
    info.append("\nTrace Design:")
    info.append(f"  Width: {data['traces']['width']:.3f}mm")
    info.append(f"  Spacing: {data['traces']['spacing']:.3f}mm")
    info.append(f"  Turns per layer: {data['traces']['turns_per_layer']}")
    info.append(f"  Total layers: {data['traces']['total_layers']}")
    info.append(f"  Total length: {data['traces']['total_length']:.2f}m")
    
    # Electrical
    info.append("\nElectrical Properties:")
    info.append(f"  Resistance: {data['electrical']['resistance']:.2f}Ω")
    info.append(f"  Voltage: {data['electrical']['voltage']:.1f}V")
    info.append(f"  Current: {data['electrical']['current']:.3f}A")
    info.append(f"  Current density: {data['electrical']['current_density']:.2f}A/mm²")
    info.append(f"  Power: {data['electrical']['power']:.2f}W")
    
    # Thermal
    info.append("\nThermal Analysis:")
    info.append("  Space Operation:")
    info.append(f"    Ambient: {data['thermal']['space']['ambient']:.1f}°C")
    info.append(f"    Rise: {data['thermal']['space']['temperature_rise']:.1f}°C")
    info.append(f"    Final: {data['thermal']['space']['final_temperature']:.1f}°C")

    # Dynamics
    info.append("\nDynamics Analysis:")
    info.append(f"    Inductance: {data['dynamics']['inductance']:.1f}μH")
    info.append(f"    Time constant: {data['dynamics']['time_constant']}ms")
    info.append(f"    Time to 99% of magnetic moment: {data['dynamics']['time_to_99_percent']}ms")
    info.append(f"    99% of magnetic moment: {data['dynamics']['max_moment_99_percent']} A·m²")
    
    # Performance
    info.append("\nPerformance:")
    info.append(f"  Magnetic moment: {data['performance']['magnetic_moment']} A·m²")
    
    return '\n'.join(info)

def generate_spiral_coordinates(params, layer_idx):
    """Generate coordinates for a realistic spiral with connections between turns"""
    inner_length = params['inner_length']
    inner_width = params['inner_width']
    outer_length = params['outer_length']
    outer_width = params['outer_width']
    trace_width = params['trace_width']
    trace_spacing = params['trace_spacing']
    num_turns = params['num_turns']
    
    paths = []
    turn_length = trace_spacing + trace_width
    
    # Start from outer edge
    for n in range(num_turns):
        # Calculate dimensions for this turn
        y_track_length = outer_length - 2*n*(trace_spacing+trace_width)
        x_track_length = outer_width - 2*n*(trace_spacing+trace_width)
        
        # Calculate starting positions
        x_start = -outer_width/2 + n*(trace_spacing+trace_width)
        y_start = -outer_length/2 + n*(trace_spacing+trace_width)
        x_end = x_start + x_track_length
        y_end = y_start + y_track_length
        y_2_end = y_end - trace_spacing - trace_width
        x_2_end = x_start + trace_spacing + trace_width
        
        # First turn special handling
        if n == 0:
            if layer_idx == 0:
                # Input connection
                paths.append(([x_start, x_start], 
                            [y_end-turn_length, y_end+1.5*turn_length]))
            else:
                # Connection to previous layer
                paths.extend([
                    ([x_start, x_start+turn_length], 
                     [y_end-turn_length, y_end]),
                    ([x_start+turn_length, x_start+2*(layer_idx+1)*turn_length+5], 
                     [y_end, y_end]),
                    ([x_start+2*(layer_idx+1)*turn_length+5, x_start+2*(layer_idx+1)*turn_length+6.5*turn_length], 
                     [y_end, y_end+1.5*turn_length])
                ])
        
        # Main spiral segments
        paths.extend([
            # Left vertical
            ([x_start, x_start], [y_start+turn_length, y_end-turn_length]),
            # Top left corner
            ([x_start, x_start+turn_length], [y_start+turn_length, y_start]),
            # Top horizontal
            ([x_start+turn_length, x_end-turn_length], [y_start, y_start]),
            # Top right corner
            ([x_end-turn_length, x_end], [y_start, y_start+turn_length]),
            # Right vertical
            ([x_end, x_end], [y_start+turn_length, y_2_end-turn_length]),
            # Bottom right corner
            ([x_end, x_end-turn_length], [y_2_end-turn_length, y_2_end])
        ])
        
        # Last turn special handling
        if n == num_turns-1:
            x_end_final = x_2_end+2*(layer_idx+1)*turn_length
            paths.extend([
                # Bottom connection
                ([x_end-turn_length, x_end_final], [y_2_end, y_2_end]),
                # Final vertical segment
                ([x_end_final, x_end_final-turn_length], 
                 [y_2_end, y_2_end-1.5*turn_length])
            ])
        else:
            paths.extend([
                # Bottom horizontal
                ([x_end-turn_length, x_2_end+turn_length], [y_2_end, y_2_end]),
                # Bottom left corner
                ([x_2_end+turn_length, x_2_end], [y_2_end, y_2_end-turn_length])
            ])
    
    return paths

def plot_layer(paths, params, design_data, layer_num, output_dir):
    """Plot a single layer with realistic wire routing and complete design information"""
    # Create figure with adjusted size for info panel
    plt.figure(figsize=(12, 8))
    
    # Create subplot layout: main plot and info panel
    gs = plt.GridSpec(1, 2, width_ratios=[2, 1])
    ax_main = plt.subplot(gs[0])
    ax_info = plt.subplot(gs[1])
    
    # Plot main design on left subplot
    if layer_num < params['num_layers'] - 1:
        colors = plt.cm.viridis(np.linspace(0, 0.8, len(paths)))
        for path, color in zip(paths, colors):
            # For each segment in the path
            x, y = path[0], path[1]
            for i in range(len(x)-1):
                # Get start and end points of segment
                x1, y1 = x[i], y[i]
                x2, y2 = x[i+1], y[i+1]
                
                # Calculate angle of line
                angle = np.arctan2(y2-y1, x2-x1)
                
                # Calculate rectangle corners
                half_width = params['trace_width']/2
                dx = half_width * np.sin(angle)
                dy = half_width * np.cos(angle)
                
                # Create rectangle for this trace segment
                rect_coords = [
                    [x1-dx, y1+dy],
                    [x2-dx, y2+dy],
                    [x2+dx, y2-dy],
                    [x1+dx, y1-dy]
                ]
                
                rect = plt.Polygon(rect_coords, facecolor=color, edgecolor=None)
                ax_main.add_patch(rect)
    
    else:
        # H-bridge connection layer
        connector_width = 5.0
        connector_length = 8.0
        pin_radius = 0.6
        
        conn_x = params['outer_width']/2 + 1
        conn_y = 0
        
        connector = plt.Rectangle((conn_x, conn_y - connector_length/2),
                                connector_width, connector_length,
                                facecolor='lightgray', edgecolor='black')
        ax_main.add_patch(connector)
        
        pin_y_positions = [conn_y - 2, conn_y + 2]
        pin_x = conn_x + connector_width/2
        
        for i, pin_y in enumerate(pin_y_positions):
            pin = plt.Circle((pin_x, pin_y), pin_radius, 
                           facecolor='gold', edgecolor='black')
            ax_main.add_patch(pin)
            label = 'I' if i == 0 else 'O'
            ax_main.text(pin_x + 2*pin_radius, pin_y, label,
                      ha='left', va='center')
    
    # Draw board outline
    ax_main.add_patch(plt.Rectangle((-params['outer_width']/2, -params['outer_length']/2),
                                  params['outer_width'], params['outer_length'],
                                  fill=False, color='black', linewidth=2))
    ax_main.add_patch(plt.Rectangle((-params['inner_width']/2, -params['inner_length']/2),
                                  params['inner_width'], params['inner_length'],
                                  fill=False, color='black', linewidth=2))
    
    # Configure main plot
    ax_main.set_aspect('equal')
    margin = max(params['outer_width'], params['outer_length']) * 0.2
    ax_main.set_xlim(-params['outer_width']/2 - margin, params['outer_width']/2 + margin*1.5)
    ax_main.set_ylim(-params['outer_length']/2 - margin, params['outer_length']/2 + margin)
    
    title = f'Layer {layer_num + 1}' + (' (H-Bridge Connections)' if layer_num == params['num_layers'] - 1 else '')
    ax_main.set_title(title)
    ax_main.grid(True, linestyle='--', alpha=0.3)
    
    # Add complete design information to right subplot
    ax_info.axis('off')
    info_text = format_design_info(design_data)
    ax_info.text(0, 1, info_text, 
                fontsize=8, fontfamily='monospace',
                verticalalignment='top',
                bbox=dict(facecolor='white', alpha=0.8, pad=10))
    
    # Adjust layout and save
    plt.tight_layout()
    output_path = os.path.join(output_dir, f'magnetorquer_layer_{layer_num + 1}.png')
    plt.savefig(output_path, dpi=350, bbox_inches='tight')
    print(f"Successfully saved {output_path}")

def plot_magnetorquer(design_data):
    """Create visualization of all layers with complete design information"""
    output_dir = ensure_output_directory()
    
    params = {
        'inner_length': design_data['dimensions']['inner']['length'],
        'inner_width': design_data['dimensions']['inner']['width'],
        'outer_length': design_data['dimensions']['outer']['length'],
        'outer_width': design_data['dimensions']['outer']['width'],
        'trace_width': design_data['traces']['width'],
        'trace_spacing': design_data['traces']['spacing'],
        'num_turns': design_data['traces']['turns_per_layer'],
        'num_layers': design_data['traces']['total_layers']
    }
    
    for i in range(params['num_layers']):
        paths = generate_spiral_coordinates(params, i)
        plot_layer(paths, params, design_data, i, output_dir)
    
    plt.show()

if __name__ == "__main__":
    try:
        with open('design.json', 'r') as f:
            design_data = json.load(f)
        plot_magnetorquer(design_data)
    except Exception as e:
        print(f"Error: {e}")