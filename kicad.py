#!/usr/bin/env python3

"""
Optimized KiCad script for magnetorquer coil generation
Run this directly in KiCad's PCB Editor Python Console (Tools > Scripting Console)

USAGE: put into the KiCad python console function by function, and then run main() at the end! update DESIGN_PARAMS to reflect design.json file
"""

from pcbnew import *

# Design parameters (previously in design.json)
DESIGN_PARAMS = {
  "dimensions": {
    "inner": {
      "length": 97.0,
      "width": 25.0
    },
    "outer": {
      "length": 132.0,
      "width": 61.0
    }
  },
  "traces": {
    "width": 0.45,
    "spacing": 0.1,
    "turns_per_layer": 29,
    "total_layers": 6,
    "total_length": 47.2
  },
  "electrical": {
    "resistance": 25.39,
    "voltage": 8.2,
    "current": 0.323,
    "power": 2.65,
    "current_density": 10.34,
    "inductance": 836.99
  },
  "thermal": {
    "ground_test": {
      "ambient": 20.0,
      "temperature_rise": 27.8,
      "final_temperature": 47.8
    },
    "space": {
      "ambient": 0.0,
      "temperature_rise": 33.0,
      "final_temperature": 33.0
    }
  },
  "performance": {
    "magnetic_moment": 0.253
  }
}

def get_inner_copper_layer_ids(board):
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
    v.SetLayerPair(0, 31)  # Connect F.Cu to B.Cu
    board.Add(v)

def main():
    board = GetBoard()
    if not board:
        print("Error: No board found. Please open a PCB file first.")
        return

    delete_all_tracks(board)

    # Extract parameters from DESIGN_PARAMS
    trace_width = DESIGN_PARAMS['traces']['width']
    trace_spacing = DESIGN_PARAMS['traces']['spacing']
    n_turns = DESIGN_PARAMS['traces']['turns_per_layer']
    n_layers = DESIGN_PARAMS['traces']['total_layers'] - 1  # excluding H-bridge layer

    # Board dimensions
    x_max = DESIGN_PARAMS['dimensions']['outer']['width']
    y_max = DESIGN_PARAMS['dimensions']['outer']['length']
    x_min = DESIGN_PARAMS['dimensions']['inner']['width']
    y_min = DESIGN_PARAMS['dimensions']['inner']['length']

    # Calculate starting position relative to board center for proper placement
    board_info = board.GetBoardEdgesBoundingBox()
    center_x = board_info.GetCenter().x / 1000000  # Convert from internal units to mm
    center_y = board_info.GetCenter().y / 1000000
    
    # # Start position will be half the outer dimensions from center
    # start_position = (center_x - x_max/2, center_y - y_max/2)
    # Put it outside board, we will move it over anyways
    start_position = (300, 300)
    bottom_offset = 5.0
    connection_layer = board.GetLayerID("B.Cu")

    layer_ids = get_inner_copper_layer_ids(board)
    layer_ids.insert(0, board.GetLayerID("F.Cu"))

    starting_layers = range(len(layer_ids))
    end_via_locations = []

    for layer_idx in range(len(layer_ids)):
        for n in range(n_turns):
            turn_length = trace_spacing + trace_width
            y_track_length = y_max - 2*(n)*(trace_spacing+trace_width)
            x_track_length = x_max - 2*(n)*(trace_spacing+trace_width)
            
            # Starting positions calculating from center
            x_start = start_position[0] + n*(trace_spacing+trace_width)
            y_start = start_position[1] + n*(trace_spacing+trace_width)
            y_end = y_start + y_track_length
            y_2_end = y_end - trace_spacing - trace_width
            x_end = x_start + x_track_length
            x_2_end = x_start + trace_spacing + trace_width

            # First turn special case - matching 2D visualization
            if n == 0:
                if layer_idx == 0:
                    # Input connection
                    draw_trace(board, x_start, y_end-turn_length, x_start, 
                             y_end+1.5*turn_length, trace_width, layer_ids[layer_idx])
                else:
                    # Connection to previous layer with correct offset
                    draw_trace(board, x_start, y_end-turn_length, x_start+turn_length, 
                             y_end, trace_width, layer_ids[layer_idx])
                    draw_trace(board, x_start+turn_length, y_end, 
                             x_start+2*(layer_idx+1)*turn_length+5, y_end, 
                             trace_width, layer_ids[layer_idx])
                    draw_trace(board, x_start+2*(layer_idx+1)*turn_length+5, y_end,
                             x_start+2*(layer_idx+1)*turn_length+6.5*turn_length,
                             y_end+1.5*turn_length, trace_width, layer_ids[layer_idx])
                    
                    # Via placement matching visualization pattern
                    draw_via(board, x_start+2*(layer_idx+1)*turn_length+6.5*turn_length,
                            y_end+1.5*turn_length, 0.3, 0.6)
                    
                    if len(end_via_locations) > 0:
                        draw_trace(board, x_start+2*(layer_idx+1)*turn_length+6.5*turn_length,
                                 y_end+1.5*turn_length, end_via_locations[-1][0], 
                                 end_via_locations[-1][1], trace_width, connection_layer)

            # Main spiral traces
            draw_trace(board, x_start, y_start+turn_length, x_start, y_end-turn_length, 
                      trace_width, layer_ids[layer_idx])
            draw_trace(board, x_start, y_start+turn_length, x_start+turn_length, 
                      y_start, trace_width, layer_ids[layer_idx])
            draw_trace(board, x_start+turn_length, y_start, x_end-turn_length, 
                      y_start, trace_width, layer_ids[layer_idx])
            draw_trace(board, x_end-turn_length, y_start, x_end, y_start+turn_length, 
                      trace_width, layer_ids[layer_idx])
            draw_trace(board, x_end, y_start+turn_length, x_end, y_2_end-turn_length, 
                      trace_width, layer_ids[layer_idx])
            draw_trace(board, x_end, y_2_end-turn_length, x_end-turn_length, y_2_end, 
                      trace_width, layer_ids[layer_idx])

            if n == n_turns-1:
                # Final turn connections matching visualization
                x_end_final = x_2_end+2*(layer_idx+1)*turn_length
                draw_trace(board, x_end-turn_length, y_2_end, x_end_final, y_2_end, 
                          trace_width, layer_ids[layer_idx])
                draw_trace(board, x_end_final, y_2_end, x_end_final-turn_length,
                          y_2_end-1.5*turn_length, trace_width, layer_ids[layer_idx])
                draw_via(board, x_end_final-turn_length, y_2_end-1.5*turn_length, 0.3, 0.6)
                end_via_locations.append([x_end_final-turn_length, y_2_end-1.5*turn_length])
            else:
                draw_trace(board, x_end-turn_length, y_2_end, x_2_end+turn_length, 
                          y_2_end, trace_width, layer_ids[layer_idx])
                draw_trace(board, x_2_end+turn_length, y_2_end, x_2_end, 
                          y_2_end-turn_length, trace_width, layer_ids[layer_idx])

    print(f"Successfully generated {n_turns} turns across {n_layers} layers")
    print(f"Total tracks: {len(board.GetTracks())}")
    Refresh()

main()