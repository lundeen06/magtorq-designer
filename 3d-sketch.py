import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import json
from typing import List, Tuple

def parse_json_file(filename: str) -> dict:
    """Parse the design output JSON file"""
    with open(filename, 'r') as f:
        return json.load(f)

def generate_spiral_coordinates(params: dict) -> List[Tuple[List[float], List[float]]]:
    """Generate coordinates for the spiral with inner cutout, properly centered"""
    inner_length = params['dimensions']['inner']['length']
    inner_width = params['dimensions']['inner']['width']
    outer_length = params['dimensions']['outer']['length']
    outer_width = params['dimensions']['outer']['width']
    trace_width = params['traces']['width']
    trace_spacing = params['traces']['spacing']
    num_turns = params['traces']['turns_per_layer']
    
    paths = []
    
    for i in range(num_turns):
        offset = i * (trace_width + trace_spacing)
        width = outer_width - 2 * offset
        length = outer_length - 2 * offset
        
        half_width = width / 2
        half_length = length / 2
        
        turn_x = [-half_width, half_width, half_width, -half_width, -half_width]
        turn_y = [-half_length, -half_length, half_length, half_length, -half_length]
        
        paths.append((turn_x, turn_y))
        
        next_width = outer_width - 2 * (offset + trace_width + trace_spacing)
        next_length = outer_length - 2 * (offset + trace_width + trace_spacing)
        if next_width <= inner_width or next_length <= inner_length:
            break
    
    return paths


def format_json_for_display(data: dict) -> str:
    """Format the design data for display in a neat, organized manner"""
    info_text = "<b>Design Specifications</b><br><br>"
    
    # Dimensions section
    info_text += "<b>Dimensions</b><br>"
    info_text += f"Inner: {data['dimensions']['inner']['length']:.1f}mm × {data['dimensions']['inner']['width']:.1f}mm<br>"
    info_text += f"Outer: {data['dimensions']['outer']['length']:.1f}mm × {data['dimensions']['outer']['width']:.1f}mm<br><br>"
    
    # Traces section
    info_text += "<b>Traces</b><br>"
    info_text += f"Width: {data['traces']['width']:.3f}mm<br>"
    info_text += f"Spacing: {data['traces']['spacing']:.3f}mm<br>"
    info_text += f"Turns per layer: {data['traces']['turns_per_layer']}<br>"
    info_text += f"Total layers: {data['traces']['total_layers']}<br>"
    info_text += f"Total length: {data['traces']['total_length']:.2f}mm<br><br>"
    
    # Electrical characteristics
    info_text += "<b>Electrical</b><br>"
    info_text += f"Resistance: {data['electrical']['resistance']:.2f}Ω<br>"
    info_text += f"Voltage: {data['electrical']['voltage']:.1f}V<br>"
    info_text += f"Current: {data['electrical']['current']:.3f}A<br>"
    info_text += f"Current density: {data['electrical']['current_density']:.2f}A/mm²<br>"
    info_text += f"Power: {data['electrical']['power']:.2f}W<br><br>"
    
    # Thermal characteristics
    info_text += "<b>Thermal</b><br>"
    info_text += f"Temperature rise: {data['thermal']['temperature_rise']:.1f}°C<br>"
    info_text += f"Final temperature: {data['thermal']['final_temperature']:.1f}°C<br><br>"
    
    # Performance
    info_text += "<b>Performance</b><br>"
    info_text += f"Magnetic moment: {data['performance']['magnetic_moment']} A·m²"
    
    return info_text

def transform_coordinates(x: list, y: list, position: tuple, rotation_deg: float):
    """Transform coordinates based on position and rotation"""
    # Convert rotation to radians
    theta = np.radians(rotation_deg)
    
    # Create rotation matrix
    cos_theta = np.cos(theta)
    sin_theta = np.sin(theta)
    
    # Transform each point
    transformed_x = []
    transformed_y = []
    
    for px, py in zip(x, y):
        # Rotate point
        rotated_x = px * cos_theta - py * sin_theta
        rotated_y = px * sin_theta + py * cos_theta
        
        # Translate point
        final_x = rotated_x + position[0]
        final_y = rotated_y + position[1]
        
        transformed_x.append(final_x)
        transformed_y.append(final_y)
    
    return transformed_x, transformed_y

def add_molex_connector(fig: go.Figure, params: dict, z_top: float, 
                       position: tuple = None, rotation_deg: float = 0):
    """Add Molex connector visualization with IO pins, with configurable position and rotation
    
    Args:
        fig: Plotly figure object
        params: Design parameters dictionary
        z_top: Z-coordinate for top layer
        position: (x, y) tuple for connector position. If None, defaults to left side.
        rotation_deg: Rotation in degrees (clockwise from vertical)
    """
    connector_width = 5.0
    connector_length = 8.0
    pin_radius = 0.6
    
    # Calculate the radius of the outermost spiral turn
    outer_turn_width = params['dimensions']['outer']['width']
    outer_turn_length = params['dimensions']['outer']['length']
    
    # Default position if none provided
    if position is None:
        position = (-outer_turn_width/2 - connector_width, 0)  # Left side default
    
    # Create base connector outline (anchored at left edge)
    base_x = [0, connector_width, connector_width, 0, 0]
    base_y = [-connector_length/2, -connector_length/2, connector_length/2, connector_length/2, -connector_length/2]
    
    # Transform connector outline
    x, y = transform_coordinates(base_x, base_y, position, rotation_deg)
    z = [z_top] * 5
    
    # Create a "dummy" trace for the connector layer group
    fig.add_trace(
        go.Scatter3d(
            x=[None], y=[None], z=[None],
            mode='lines',
            name='Connector Layer',
            legendgroup='connector_layer',
            legendgrouptitle_text='Connector Layer',
            showlegend=True
        ),
        row=1, col=1
    )
    
    # Add connector outline
    fig.add_trace(
        go.Scatter3d(
            x=x, y=y, z=z,
            mode='lines',
            line=dict(color='darkgray', width=3),
            name='Connector',
            legendgroup='connector_layer',
            showlegend=False
        ),
        row=1, col=1
    )
    
    # Create base pin positions (relative to left edge)
    base_pin_positions = [
        (connector_width/2, -connector_length/4, 'I'),  # Input pin
        (connector_width/2, connector_length/4, 'O')    # Output pin
    ]
    
    # Transform and store actual pin positions
    pin_positions = []
    for base_px, base_py, label in base_pin_positions:
        # Transform pin center
        px, py = transform_coordinates([base_px], [base_py], position, rotation_deg)
        pin_positions.append((px[0], py[0], label))
        
        # Create and transform circle points for pin
        theta = np.linspace(0, 2*np.pi, 20)
        circle_base_x = pin_radius * np.cos(theta)
        circle_base_y = pin_radius * np.sin(theta)
        
        # Transform circle points
        circle_x, circle_y = transform_coordinates(
            circle_base_x + base_px,
            circle_base_y + base_py,
            position, rotation_deg
        )
        circle_z = [z_top] * len(theta)
        
        fig.add_trace(
            go.Scatter3d(
                x=circle_x, y=circle_y, z=circle_z,
                mode='lines',
                line=dict(color='gold', width=2),
                name=f'Pin {label}',
                legendgroup='connector_layer',
                showlegend=False
            ),
            row=1, col=1
        )
    
    # Calculate coil connection point based on rotation
    coil_x = -outer_turn_width/2
    
    # Add connecting traces with proper routing based on rotation
    for pin_pos in pin_positions:
        fig.add_trace(
            go.Scatter3d(
                x=[pin_pos[0], coil_x],
                y=[pin_pos[1], pin_pos[1]],
                z=[z_top, z_top],
                mode='lines',
                line=dict(color='gold', width=2),
                name=f'{pin_pos[2]} Connection',
                legendgroup='connector_layer',
                showlegend=False
            ),
            row=1, col=1
        )
    
    return position[0], position[1]

def create_3d_visualization(design_data: dict):
    """Create an interactive 3D visualization with 2D info panel"""
    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{"type": "scene"}, {"type": "xy"}]],
        column_widths=[0.7, 0.3],
        horizontal_spacing=0.02
    )
    
    params = {
        'dimensions': design_data['dimensions'],
        'traces': design_data['traces']
    }
    
    paths = generate_spiral_coordinates(params)
    
    # PCB thickness and layer spacing
    pcb_thickness = 1.6
    layer_spacing = pcb_thickness / (params['traces']['total_layers'] + 1)
    
    # Define metallic colors for alternating traces
    trace_colors = ['#FFD700', '#C0C0C0']  # Gold and Silver
    
    # Add traces for each layer
    for layer in range(params['traces']['total_layers'] - 1):
        z_offset = layer * layer_spacing
        
        # Create a "dummy" trace for the layer group
        fig.add_trace(
            go.Scatter3d(
                x=[None], y=[None], z=[None],
                mode='lines',
                name=f'Layer {layer + 1}',
                legendgroup=f'layer{layer + 1}',
                legendgrouptitle_text=f'Layer {layer + 1}',
                showlegend=True
            ),
            row=1, col=1
        )
        
        # Add all turns and vias for this layer
        for i, (x, y) in enumerate(paths):
            x = np.array(x)
            y = np.array(y)
            z = np.full_like(x, z_offset)
            
            # Alternate between gold and silver for each turn
            color = trace_colors[i % len(trace_colors)]
            
            # Add spiral turn
            fig.add_trace(
                go.Scatter3d(
                    x=x, y=y, z=z,
                    mode='lines',
                    line=dict(color=color, width=3),
                    name=f'Turn {i + 1}',
                    legendgroup=f'layer{layer + 1}',
                    showlegend=False
                ),
                row=1, col=1
            )
            
            # Add via to next turn if not last turn
            if i < len(paths) - 1:
                next_x = paths[i + 1][0][-1]
                next_y = paths[i + 1][1][-1]
                via_x = [x[-1], next_x]
                via_y = [y[-1], next_y]
                via_z = [z[-1], z[-1]]
                
                # Use the same color as the current turn for its via
                fig.add_trace(
                    go.Scatter3d(
                        x=via_x, y=via_y, z=via_z,
                        mode='lines',
                        line=dict(color=color, width=2, dash='dot'),
                        name=f'Via {i + 1}',
                        legendgroup=f'layer{layer + 1}',
                        showlegend=False
                    ),
                    row=1, col=1
                )
    
    # Add top layer components
    z_top = (params['traces']['total_layers'] - 1) * layer_spacing
    
    # Add Molex connector with alternating gold/silver connections
    outer_turn_width = params['dimensions']['outer']['width']
    outer_turn_length = params['dimensions']['outer']['length']
    connector_width = 5.0
    connector_length = 8.0
    position = (-outer_turn_width/2 - connector_width, outer_turn_length/2 - connector_length/2)
    
    # Modified add_molex_connector function inline to handle alternating colors
    connector_width = 5.0
    connector_length = 8.0
    pin_radius = 0.6
    
    # Create base connector outline
    base_x = [0, connector_width, connector_width, 0, 0]
    base_y = [-connector_length/2, -connector_length/2, connector_length/2, connector_length/2, -connector_length/2]
    
    # Transform connector outline
    x, y = transform_coordinates(base_x, base_y, position, 0)
    z = [z_top] * 5
    
    # Add connector outline
    fig.add_trace(
        go.Scatter3d(
            x=x, y=y, z=z,
            mode='lines',
            line=dict(color='darkgray', width=3),
            name='Connector',
            legendgroup='connector_layer',
            showlegend=True
        ),
        row=1, col=1
    )
    
    # Create base pin positions
    base_pin_positions = [
        (connector_width/2, -connector_length/4, 'I'),
        (connector_width/2, connector_length/4, 'O')
    ]
    
    # Add pins with alternating colors
    for idx, (base_px, base_py, label) in enumerate(base_pin_positions):
        # Transform pin center
        px, py = transform_coordinates([base_px], [base_py], position, 0)
        
        # Create circle points for pin
        theta = np.linspace(0, 2*np.pi, 20)
        circle_base_x = pin_radius * np.cos(theta)
        circle_base_y = pin_radius * np.sin(theta)
        
        # Transform circle points
        circle_x, circle_y = transform_coordinates(
            circle_base_x + base_px,
            circle_base_y + base_py,
            position, 0
        )
        circle_z = [z_top] * len(theta)
        
        # Alternate between gold and silver
        pin_color = trace_colors[idx % len(trace_colors)]
        
        fig.add_trace(
            go.Scatter3d(
                x=circle_x, y=circle_y, z=circle_z,
                mode='lines',
                line=dict(color=pin_color, width=2),
                name=f'Pin {label}',
                legendgroup='connector_layer',
                showlegend=False
            ),
            row=1, col=1
        )
        
        # Add connecting traces
        coil_x = -outer_turn_width/2
        fig.add_trace(
            go.Scatter3d(
                x=[px[0], coil_x],
                y=[py[0], py[0]],
                z=[z_top, z_top],
                mode='lines',
                line=dict(color=pin_color, width=2),
                name=f'{label} Connection',
                legendgroup='connector_layer',
                showlegend=False
            ),
            row=1, col=1
        )
    
    # Add top layer components
    z_top = (params['traces']['total_layers'] - 1) * layer_spacing
    
    # Add Molex connector
    # Position at bottom left, connector starts exactly at the specified position
    outer_turn_width = params['dimensions']['outer']['width']
    outer_turn_length = params['dimensions']['outer']['length']
    connector_width = 5.0
    connector_length = 8.0

    position = (-outer_turn_width/2 - connector_width, outer_turn_length/2 - connector_length/2)
    add_molex_connector(fig, params, z_top, position=position, rotation_deg=0)
    
    # Add PCB outline and inner cutout at bottom and top
    outline_pairs = [
        (
            [-params['dimensions']['outer']['width']/2, params['dimensions']['outer']['width']/2,
             params['dimensions']['outer']['width']/2, -params['dimensions']['outer']['width']/2,
             -params['dimensions']['outer']['width']/2],
            [-params['dimensions']['outer']['length']/2, -params['dimensions']['outer']['length']/2,
             params['dimensions']['outer']['length']/2, params['dimensions']['outer']['length']/2,
             -params['dimensions']['outer']['length']/2],
            'PCB Outline'
        ),
        (
            [-params['dimensions']['inner']['width']/2, params['dimensions']['inner']['width']/2,
             params['dimensions']['inner']['width']/2, -params['dimensions']['inner']['width']/2,
             -params['dimensions']['inner']['width']/2],
            [-params['dimensions']['inner']['length']/2, -params['dimensions']['inner']['length']/2,
             params['dimensions']['inner']['length']/2, params['dimensions']['inner']['length']/2,
             -params['dimensions']['inner']['length']/2],
            'Inner Cutout'
        )
    ]

    for x, y, name in outline_pairs:
        for z in [0, z_top]:
            fig.add_trace(
                go.Scatter3d(
                    x=x, y=y, z=[z] * 5,
                    mode='lines',
                    line=dict(color='black', width=4),
                    name=name,
                    legendgroup='hardware',
                    showlegend=z == 0
                ),
                row=1, col=1
            )
    
    # Add version text to bottom of info panel
    info_text = format_json_for_display(design_data)
    info_text += "<br><br><span style='font-size:10px'>v1.0.0 - Generated by Magnetorquer Designer</span>"
    
    fig.add_trace(
        go.Scatter(
            x=[0], y=[0],
            mode='text',
            text=[info_text],
            textfont=dict(size=12),
            showlegend=False
        ),
        row=1, col=2
    )
    
    # Update layout for light mode
    fig.update_layout(
        title=dict(
            text='3D Magnetorquer Visualization',
            x=0.35,
            y=0.95
        ),
        scene=dict(
            aspectmode='data',
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1),
                up=dict(x=0, y=0, z=1)
            ),
            xaxis_title='Width (mm)',
            yaxis_title='Length (mm)',
            zaxis_title='Height (mm)',
            bgcolor='white'  # Light mode background
        ),
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            groupclick="togglegroup"
        ),
        paper_bgcolor='white',  # Light mode paper background
        plot_bgcolor='white'    # Light mode plot background
    )
    
    # Enable grid lines for better depth perception
    fig.update_scenes(
        xaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='lightgray',
            zeroline=True,
            zerolinewidth=2,
            zerolinecolor='gray'
        ),
        yaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='lightgray',
            zeroline=True,
            zerolinewidth=2,
            zerolinecolor='gray'
        ),
        zaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='lightgray',
            zeroline=True,
            zerolinewidth=2,
            zerolinecolor='gray'
        )
    )
    
    # Hide axes of info panel
    fig.update_xaxes(visible=False, row=1, col=2)
    fig.update_yaxes(visible=False, row=1, col=2)
    
    return fig


if __name__ == "__main__":
    try:
        design_data = parse_json_file('design.json')
        fig = create_3d_visualization(design_data)
        fig.show()
    except Exception as e:
        print(f"Error: {e}")