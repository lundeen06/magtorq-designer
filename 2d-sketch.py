import matplotlib.pyplot as plt
import numpy as np
import json
import os

def ensure_output_directory():
    """Create output directory if it doesn't exist"""
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    return output_dir

def parse_json_file(filename):
    """Parse the design output JSON file"""
    with open(filename, 'r') as f:
        data = json.load(f)
        
    return {
        'inner_length': data['dimensions']['inner']['length'],
        'inner_width': data['dimensions']['inner']['width'],
        'outer_length': data['dimensions']['outer']['length'],
        'outer_width': data['dimensions']['outer']['width'],
        'trace_width': data['traces']['width'],
        'trace_spacing': data['traces']['spacing'],
        'num_turns': data['traces']['turns_per_layer'],
        'num_layers': data['traces']['total_layers']
    }

def generate_spiral_coordinates(params):
    """Generate coordinates for the spiral with inner cutout, properly centered"""
    inner_length = params['inner_length']
    inner_width = params['inner_width']
    outer_length = params['outer_length']
    outer_width = params['outer_width']
    trace_width = params['trace_width']
    trace_spacing = params['trace_spacing']
    num_turns = params['num_turns']
    
    paths = []
    
    # Start from outer edge and work inward
    for i in range(num_turns):
        # Calculate offset from outer edge
        offset = i * (trace_width + trace_spacing)
        # Start with outer dimensions and subtract offset
        width = outer_width - 2 * offset
        length = outer_length - 2 * offset
        
        half_width = width / 2
        half_length = length / 2
        
        turn_x = [-half_width, half_width, half_width, -half_width, -half_width]
        turn_y = [-half_length, -half_length, half_length, half_length, -half_length]
        
        paths.append((turn_x, turn_y))
        
        # Check if next turn would be smaller than inner cutout
        next_width = outer_width - 2 * (offset + trace_width + trace_spacing)
        next_length = outer_length - 2 * (offset + trace_width + trace_spacing)
        if next_width <= inner_width or next_length <= inner_length:
            break
    
    return paths

def plot_layer(paths, params, layer_num, output_dir):
    """Plot a single layer with given parameters"""
    # Create a new figure for this layer (80% of original 10x10 size)
    plt.figure(figsize=(8, 8))
    ax = plt.gca()
    
    # Plot traces
    if layer_num < params['num_layers'] - 1:
        colors = plt.cm.rainbow(np.linspace(0, 1, len(paths)))
        for path, color in zip(paths, colors):
            ax.plot(path[0], path[1], '-', color=color, linewidth=1)
    else:
        # H-bridge connection layer
        pad_radius = min(params['outer_width'], params['outer_length']) * 0.1
        ax.add_patch(plt.Circle((-params['outer_width']/4, -params['outer_length']/4), 
                              pad_radius, color='red'))
        ax.add_patch(plt.Circle((params['outer_width']/4, params['outer_length']/4), 
                              pad_radius, color='red'))
        ax.text(-params['outer_width']/4, -params['outer_length']/4, 'IN', 
                ha='center', va='center', color='white')
        ax.text(params['outer_width']/4, params['outer_length']/4, 'OUT', 
                ha='center', va='center', color='white')

    # Board outlines with thicker black lines (3x original thickness)
    ax.add_patch(plt.Rectangle((-params['outer_width']/2, -params['outer_length']/2), 
                             params['outer_width'], params['outer_length'], 
                             fill=False, color='black', linewidth=3))
    ax.add_patch(plt.Rectangle((-params['inner_width']/2, -params['inner_length']/2), 
                             params['inner_width'], params['inner_length'], 
                             fill=False, color='black', linewidth=3))
    
    # Set equal aspect ratio and limits
    ax.set_aspect('equal')
    margin = max(params['outer_width'], params['outer_length']) * 0.1
    ax.set_xlim(-params['outer_width']/2 - margin, params['outer_width']/2 + margin)
    ax.set_ylim(-params['outer_length']/2 - margin, params['outer_length']/2 + margin)
    
    # Add title and grid
    title = f'Layer {layer_num + 1}' + (' (H-Bridge Connections)' if layer_num == params['num_layers'] - 1 else '')
    ax.set_title(title)
    ax.grid(True, linestyle='--', alpha=0.3)
    
    # Add design parameters as text
    text_params = (
        f"Outer dimensions: {params['outer_length']:.1f}mm × {params['outer_width']:.1f}mm\n"
        f"Inner dimensions: {params['inner_length']:.1f}mm × {params['inner_width']:.1f}mm\n"
        f"Trace width: {params['trace_width']:.3f}mm\n"
        f"Spacing: {params['trace_spacing']:.3f}mm\n"
        f"Turns per layer: {params['num_turns']}"
    )
    
    plt.figtext(0.1, 0.02, text_params, fontsize=10, 
                bbox=dict(facecolor='white', alpha=0.8))
    
    # Save individual layer to output directory
    output_path = os.path.join(output_dir, f'magnetorquer_layer_{layer_num + 1}.png')
    try:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"Successfully saved {output_path}")
    except Exception as e:
        print(f"Error saving figure for layer {layer_num + 1}: {e}")
        print("Trying with reduced DPI...")
        plt.savefig(output_path, dpi=100, bbox_inches='tight')

def plot_magnetorquer(params):
    """Create visualization of all layers"""
    # Ensure output directory exists
    output_dir = ensure_output_directory()
    
    paths = generate_spiral_coordinates(params)
    
    # Plot each layer in a separate window
    for i in range(params['num_layers']):
        plot_layer(paths, params, i, output_dir)
    
    # Show all plots
    plt.show()

if __name__ == "__main__":
    try:
        params = parse_json_file('design.json')
        plot_magnetorquer(params)
    except Exception as e:
        print(f"Error: {e}")