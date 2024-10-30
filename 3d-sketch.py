import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import json
from typing import List, Tuple

def generate_spiral_coordinates(params: dict, layer_idx: int) -> List[Tuple[List[float], List[float]]]:
    """Generate coordinates for a realistic spiral with connections between turns"""
    inner_length = params['dimensions']['inner']['length']
    inner_width = params['dimensions']['inner']['width']
    outer_length = params['dimensions']['outer']['length']
    outer_width = params['dimensions']['outer']['width']
    trace_width = params['traces']['width']
    trace_spacing = params['traces']['spacing']
    num_turns = params['traces']['turns_per_layer']
    
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
        
        current_path = []
        
        # First turn special handling
        if n == 0:
            if layer_idx == 0:
                # Input connection
                current_path.extend([
                    (x_start, y_end-turn_length),
                    (x_start, y_end+1.5*turn_length)
                ])
            else:
                # Connection to previous layer
                current_path.extend([
                    (x_start, y_end-turn_length),
                    (x_start+turn_length, y_end),
                    (x_start+2*(layer_idx+1)*turn_length+5, y_end),
                    (x_start+2*(layer_idx+1)*turn_length+6.5*turn_length, y_end+1.5*turn_length)
                ])
        
        # Main spiral segments
        current_path.extend([
            (x_start, y_start+turn_length),  # Start of left vertical
            (x_start, y_end-turn_length),    # End of left vertical
            (x_start+turn_length, y_start),  # Top left corner
            (x_end-turn_length, y_start),    # Top horizontal
            (x_end, y_start+turn_length),    # Top right corner
            (x_end, y_2_end-turn_length),    # Right vertical
            (x_end-turn_length, y_2_end)     # Bottom right corner
        ])
        
        # Last turn special handling
        if n == num_turns-1:
            x_end_final = x_2_end+2*(layer_idx+1)*turn_length
            current_path.extend([
                (x_end_final, y_2_end),                    # Bottom connection
                (x_end_final-turn_length, y_2_end-1.5*turn_length)  # Final vertical
            ])
        else:
            current_path.extend([
                (x_2_end+turn_length, y_2_end),  # Bottom horizontal
                (x_2_end, y_2_end-turn_length)   # Bottom left corner
            ])
        
        paths.append(current_path)
    
    return paths

def format_json_for_display(data: dict) -> str:
    """Format the design data for display in a neat, organized manner"""
    info_text = "<b>Design Specifications</b><br><br>"
    
    # Physical Dimensions
    info_text += "<b>Dimensions</b><br>"
    info_text += f"Inner: {data['dimensions']['inner']['length']:.1f}mm × {data['dimensions']['inner']['width']:.1f}mm<br>"
    info_text += f"Outer: {data['dimensions']['outer']['length']:.1f}mm × {data['dimensions']['outer']['width']:.1f}mm<br><br>"
    
    # Trace Details
    info_text += "<b>Traces</b><br>"
    info_text += f"Width: {data['traces']['width']:.3f}mm<br>"
    info_text += f"Spacing: {data['traces']['spacing']:.3f}mm<br>"
    info_text += f"Turns per layer: {data['traces']['turns_per_layer']}<br>"
    info_text += f"Total layers: {data['traces']['total_layers']}<br>"
    info_text += f"Total length: {data['traces']['total_length']:.2f}m<br><br>"
    
    # Electrical Properties
    info_text += "<b>Electrical Properties</b><br>"
    info_text += f"Resistance: {data['electrical']['resistance']:.2f}Ω<br>"
    info_text += f"Voltage: {data['electrical']['voltage']:.1f}V<br>"
    info_text += f"Current: {data['electrical']['current']:.3f}A<br>"
    info_text += f"Current density: {data['electrical']['current_density']:.2f}A/mm²<br>"
    info_text += f"Power: {data['electrical']['power']:.2f}W<br>"
    info_text += f"Inductance: {data['electrical']['inductance']}µH<br><br>"
    
    # Thermal Analysis
    info_text += "<b>Thermal Analysis</b><br>"
    info_text += "<i>Ground Test:</i><br>"
    info_text += f"• Ambient: {data['thermal']['ground_test']['ambient']:.1f}°C<br>"
    info_text += f"• Temperature rise: {data['thermal']['ground_test']['temperature_rise']:.1f}°C<br>"
    info_text += f"• Final temperature: {data['thermal']['ground_test']['final_temperature']:.1f}°C<br>"
    info_text += "<br>"
    info_text += "<i>Space Operation:</i><br>"
    info_text += f"• Ambient: {data['thermal']['space']['ambient']:.1f}°C<br>"
    info_text += f"• Temperature rise: {data['thermal']['space']['temperature_rise']:.1f}°C<br>"
    info_text += f"• Final temperature: {data['thermal']['space']['final_temperature']:.1f}°C<br><br>"
    
    # Performance Metrics
    info_text += "<b>Performance</b><br>"
    info_text += f"Magnetic moment: {data['performance']['magnetic_moment']} A·m²"
    
    return info_text

def create_3d_visualization(design_data: dict):
    """Create an interactive 3D visualization with realistic wire routing"""
    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{"type": "scene"}, {"type": "xy"}]],
        column_widths=[0.7, 0.3],
        horizontal_spacing=0.02
    )
    
    # PCB thickness and layer spacing
    pcb_thickness = 1.6
    n_layers = design_data['traces']['total_layers']
    layer_spacing = pcb_thickness / (n_layers + 1)
    
    # Define metallic colors for traces
    # trace_colors = ['#FFD700', '#C0C0C0']  # Gold and Silver
    trace_colors = ['#B87333', '#CD7F32']  # Copper tones
    
    # Generate and plot traces for each layer
    for layer in range(n_layers - 1):  # Exclude H-bridge layer
        z_offset = layer * layer_spacing
        
        # Generate paths for this layer
        paths = generate_spiral_coordinates(design_data, layer)
        
        # Create a dummy trace for layer group
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
        
        # Plot each turn in the spiral
        for i, path in enumerate(paths):
            x_coords = [p[0] for p in path]
            y_coords = [p[1] for p in path]
            z_coords = [z_offset] * len(path)
            
            # Alternate between gold and silver
            color = trace_colors[i % len(trace_colors)]
            
            # Add the trace
            fig.add_trace(
                go.Scatter3d(
                    x=x_coords,
                    y=y_coords,
                    z=z_coords,
                    mode='lines',
                    line=dict(color=color, width=3),
                    name=f'Turn {i + 1}',
                    legendgroup=f'layer{layer + 1}',
                    showlegend=False
                ),
                row=1, col=1
            )
            
            # Add vias between layers
            if layer > 0 and i == 0:  # Input via
                via_x = path[3][0]  # Connection point x
                via_y = path[3][1]  # Connection point y
                via_z = [z_offset - layer_spacing, z_offset]
                
                fig.add_trace(
                    go.Scatter3d(
                        x=[via_x, via_x],
                        y=[via_y, via_y],
                        z=via_z,
                        mode='lines',
                        line=dict(color='gold', width=4, dash='dot'),
                        name=f'Via Layer {layer}',
                        legendgroup=f'layer{layer + 1}',
                        showlegend=False
                    ),
                    row=1, col=1
                )
        
        # Add output via for each layer
        if layer < n_layers - 2:  # All except last layer
            last_path = paths[-1]
            via_x = last_path[-1][0]
            via_y = last_path[-1][1]
            via_z = [z_offset, z_offset + layer_spacing]
            
            fig.add_trace(
                go.Scatter3d(
                    x=[via_x, via_x],
                    y=[via_y, via_y],
                    z=via_z,
                    mode='lines',
                    line=dict(color='gold', width=4, dash='dot'),
                    name=f'Via Out Layer {layer}',
                    legendgroup=f'layer{layer + 1}',
                    showlegend=False
                ),
                row=1, col=1
            )
    
    # Add H-bridge layer
    z_top = (n_layers - 1) * layer_spacing
    
    # Add Molex connector
    connector_width = 5.0
    connector_length = 8.0
    outer_width = design_data['dimensions']['outer']['width']
    
    # Connector outline
    connector_x = outer_width/2 + 1
    connector_y = np.array([-connector_length/2, connector_length/2])
    connector_z = [z_top] * 2
    
    fig.add_trace(
        go.Scatter3d(
            x=[connector_x, connector_x + connector_width, connector_x + connector_width, connector_x, connector_x],
            y=[connector_y[0], connector_y[0], connector_y[1], connector_y[1], connector_y[0]],
            z=[z_top] * 5,
            mode='lines',
            line=dict(color='darkgray', width=3),
            name='Connector',
            legendgroup='connector',
            showlegend=True
        ),
        row=1, col=1
    )
    
    # Add pins
    pin_positions = [(connector_x + connector_width/2, y, z_top) for y in [-2, 2]]
    for i, (px, py, pz) in enumerate(pin_positions):
        theta = np.linspace(0, 2*np.pi, 20)
        pin_x = px + 0.6*np.cos(theta)
        pin_y = py + 0.6*np.sin(theta)
        pin_z = [pz] * 20
        
        fig.add_trace(
            go.Scatter3d(
                x=pin_x, y=pin_y, z=pin_z,
                mode='lines',
                line=dict(color='gold', width=2),
                name=f'Pin {"I" if i==0 else "O"}',
                legendgroup='connector',
                showlegend=False
            ),
            row=1, col=1
        )
    
    # Add board outline
    corners = [
        (-outer_width/2, -design_data['dimensions']['outer']['length']/2),
        (outer_width/2, -design_data['dimensions']['outer']['length']/2),
        (outer_width/2, design_data['dimensions']['outer']['length']/2),
        (-outer_width/2, design_data['dimensions']['outer']['length']/2),
        (-outer_width/2, -design_data['dimensions']['outer']['length']/2)
    ]
    
    fig.add_trace(
        go.Scatter3d(
            x=[c[0] for c in corners],
            y=[c[1] for c in corners],
            z=[0] * len(corners),
            mode='lines',
            line=dict(color='black', width=4),
            name='Board Outline',
            showlegend=True
        ),
        row=1, col=1
    )
    
    # Add inner cutout outline
    inner_corners = [
        (-design_data['dimensions']['inner']['width']/2, -design_data['dimensions']['inner']['length']/2),
        (design_data['dimensions']['inner']['width']/2, -design_data['dimensions']['inner']['length']/2),
        (design_data['dimensions']['inner']['width']/2, design_data['dimensions']['inner']['length']/2),
        (-design_data['dimensions']['inner']['width']/2, design_data['dimensions']['inner']['length']/2),
        (-design_data['dimensions']['inner']['width']/2, -design_data['dimensions']['inner']['length']/2)
    ]
    
    fig.add_trace(
        go.Scatter3d(
            x=[c[0] for c in inner_corners],
            y=[c[1] for c in inner_corners],
            z=[0] * len(inner_corners),
            mode='lines',
            line=dict(color='black', width=4),
            name='Inner Cutout',
            showlegend=True
        ),
        row=1, col=1
    )
    
    # Add info panel
    info_text = format_json_for_display(design_data)
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
    
    # Update layout
    fig.update_layout(
        title=dict(
            text='3D Magnetorquer Visualization',
            x=0.35,
            y=0.95
        ),
        scene=dict(
            aspectmode='data',
            camera=dict(
                eye=dict(x=1.8, y=1.8, z=1.2),
                up=dict(x=0, y=0, z=1)
            ),
            xaxis_title='Width (mm)',
            yaxis_title='Length (mm)',
            zaxis_title='Height (mm)',
        ),
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            groupclick="togglegroup"
        )
    )
    
    # Hide axes of info panel
    fig.update_xaxes(visible=False, row=1, col=2)
    fig.update_yaxes(visible=False, row=1, col=2)
    
    return fig

if __name__ == "__main__":
    try:
        with open('design.json', 'r') as f:
            design_data = json.load(f)
        fig = create_3d_visualization(design_data)
        fig.show()
    except Exception as e:
        print(f"Error: {e}")