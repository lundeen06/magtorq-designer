"""
Optimized KiCad script for magnetorquer coil generation
"""

from pcbnew import *

def get_inner_copper_layer_ids():
    inner_copper_count = board.GetCopperLayerCount() - 2
    layer_ids = []
    for i in range(1000):
        name = board.GetLayerName(i)
        if name != "BAD INDEX!" and name != "":
            if name.endswith(".Cu") and name != ("F.Cu") and name != ("B.Cu"):
                if float(name[2:4]) <= inner_copper_count:
                    layer_ids.append(board.GetLayerID(name))
    return layer_ids

def delete_all_tracks(board):
    tracks = board.GetTracks()
    for t in tracks:
        board.Delete(t)

def draw_trace(board, x0, y0, x1, y1, width, layer):
    try:
        track = PCB_TRACK(board)
        start_point = VECTOR2I(int(x0 * 1000000), int(y0 * 1000000))
        end_point = VECTOR2I(int(x1 * 1000000), int(y1 * 1000000))
        track.SetStart(start_point)
        track.SetEnd(end_point)
        track.SetWidth(FromMM(width))
        track.SetLayer(layer)
        board.Add(track)
    except Exception as e:
        print(f"An error occurred: {e}")

def draw_via(board, x, y, hole_size, outer_diameter):
    v = PCB_VIA(board)
    position = VECTOR2I(wxPointMM(x, y).x, wxPointMM(x, y).y)
    v.SetPosition(position)
    v.SetDrill(FromMM(hole_size))
    v.SetWidth(FromMM(outer_diameter))
    v.SetLayerPair(0, 31)
    board.Add(v)

# Load optimal parameters from design.json
with open('design.json', 'r') as f:
    design_data = json.load(f)

# Initialize board
board = GetBoard()
delete_all_tracks(board)

# Use optimized parameters from design.json
trace_width = design_data['traces']['width']  # 0.45mm
trace_spacing = design_data['traces']['spacing']  # 0.1mm
n_turns = design_data['traces']['turns_per_layer']  # 28
n_layers = design_data['traces']['total_layers'] - 1  # 5 (excluding H-bridge layer)

# Board dimensions from design.json
x_max = design_data['dimensions']['outer']['width']  # 60mm
y_max = design_data['dimensions']['outer']['length']  # 131mm
x_min = design_data['dimensions']['inner']['width']  # 25mm
y_min = design_data['dimensions']['inner']['length']  # 100mm

# Improved positioning and routing parameters
start_position = (300, 150)  # Keep existing reference point
bottom_offset = 5.0  # Reduced to minimize excess trace length
connection_layer = board.GetLayerID("B.Cu")

layer_ids = get_inner_copper_layer_ids()
layer_ids.insert(0, board.GetLayerID("F.Cu"))

# Parallel-series configuration for optimal current distribution
n_parallel = 1  # Single parallel path for maximum turns
n_series = n_layers  # All layers in series for maximum voltage handling

starting_layers = range(len(layer_ids))[::n_parallel]
end_via_locations = []

for parallel_layer_idx in starting_layers:
    for layer_idx in range(len(layer_ids))[parallel_layer_idx:parallel_layer_idx+n_series]:
        for n in range(n_turns):
            turn_length = trace_spacing + trace_width
            y_track_length = y_max - 2*(n)*(trace_spacing+trace_width)
            x_track_length = x_max - 2*(n)*(trace_spacing+trace_width)
            
            # Optimize starting positions to maximize area
            y_start = start_position[1] + n*(trace_spacing+trace_width)
            y_end = y_start + y_track_length
            y_2_end = y_end - trace_spacing - trace_width
            x_start = start_position[0] + n*(trace_spacing+trace_width)
            x_end = x_start + x_track_length
            x_2_end = x_start + trace_spacing + trace_width

            # Draw optimized spiral pattern
            if n == 0:
                if layer_idx in starting_layers:
                    height_offset = 1.2  # Reduced offset for shorter connection length
                    draw_trace(board, x_start, y_end-turn_length, x_start, y_end+(height_offset*turn_length), trace_width, layer_ids[layer_idx])
                else:
                    # Optimized series connections between layers
                    height_offset = 1.2
                    draw_trace(board, x_start, y_end-turn_length, x_start+turn_length, y_end, trace_width, layer_ids[layer_idx])
                    draw_trace(board, x_start+turn_length, y_end, x_start+(1.5*(layer_idx+1)*turn_length)+bottom_offset, y_end, trace_width, layer_ids[layer_idx])
                    draw_trace(board, x_start+(1.5*(layer_idx+1)*turn_length)+bottom_offset, y_end, 
                             x_start+(1.5*(layer_idx+1)*turn_length)+(height_offset*turn_length)+bottom_offset, 
                             y_end+height_offset*turn_length, trace_width, layer_ids[layer_idx])
                    
                    # Improved via placement for better current flow
                    draw_via(board, x_start+(1.5*(layer_idx+1)*turn_length)+(height_offset*turn_length)+bottom_offset,
                            y_end+height_offset*turn_length, 0.3, 0.6)
                    
                    if len(end_via_locations) > 0:
                        draw_trace(board, x_start+(1.5*(layer_idx+1)*turn_length)+(height_offset*turn_length)+bottom_offset,
                                 y_end+height_offset*turn_length, end_via_locations[-1][0], end_via_locations[-1][1],
                                 trace_width, connection_layer)

            # Main spiral traces with optimized spacing
            draw_trace(board, x_start, y_start+turn_length, x_start, y_end-turn_length, trace_width, layer_ids[layer_idx])
            draw_trace(board, x_start, y_start+turn_length, x_start+turn_length, y_start, trace_width, layer_ids[layer_idx])
            draw_trace(board, x_start+turn_length, y_start, x_end-turn_length, y_start, trace_width, layer_ids[layer_idx])
            draw_trace(board, x_end-turn_length, y_start, x_end, y_start+turn_length, trace_width, layer_ids[layer_idx])
            draw_trace(board, x_end, y_start+turn_length, x_end, y_2_end-turn_length, trace_width, layer_ids[layer_idx])
            draw_trace(board, x_end, y_2_end-turn_length, x_end-turn_length, y_2_end, trace_width, layer_ids[layer_idx])

            if n == n_turns-1:
                # Optimized end connections
                height_offset = 1.2
                x_end_final = x_2_end+(1.5*(layer_idx+1)*turn_length)
                draw_trace(board, x_end-turn_length, y_2_end, x_end_final, y_2_end, trace_width, layer_ids[layer_idx])
                draw_trace(board, x_end_final, y_2_end, x_end_final-turn_length, y_2_end-(turn_length*height_offset),
                          trace_width, layer_ids[layer_idx])
                draw_via(board, x_end_final-turn_length, y_2_end-(turn_length*height_offset), 0.3, 0.6)
                end_via_locations.append([x_end_final-turn_length, y_2_end-(turn_length*height_offset)])
            else:
                draw_trace(board, x_end-turn_length, y_2_end, x_2_end+turn_length, y_2_end, trace_width, layer_ids[layer_idx])
                draw_trace(board, x_2_end+turn_length, y_2_end, x_2_end, y_2_end-turn_length, trace_width, layer_ids[layer_idx])

print(f"Successfully generated {n_turns} turns across {n_layers} layers")
print(f"Total tracks: {len(board.GetTracks())}")
Refresh()