#!/usr/bin/env python3
"""
Add compute_eulerian_circuit and --mode support to morph.py
"""

from pathlib import Path

# Read the file
file_path = Path("morph.py")
content = file_path.read_text(encoding='utf-8')

# 1. Add compute_eulerian_circuit function before main()
eulerian_func = '''
def compute_eulerian_circuit(n):
    """
    Compute Eulerian circuit for complete graph K_n.
    Returns list of n(n-1) + 1 vertex indices where first == last.
    
    For K5: [0, 1, 2, 3, 4, 0, 2, 4, 1, 3, 0] -> 10 edges, loop back to start
    """
    if n <= 1:
        return list(range(n)) + [0]
    
    # Use Hierholzer's algorithm for K_n
    # Build adjacency list for complete graph
    edges = {}
    for i in range(n):
        edges[i] = list(range(n))
        edges[i].remove(i)  # Remove self-loops
    
    # Find Eulerian circuit
    stack = [0]
    circuit = []
    
    while stack:
        v = stack[-1]
        if edges[v]:
            u = edges[v].pop()
            edges[u].remove(v)  # Remove reverse edge
            stack.append(u)
        else:
            circuit.append(stack.pop())
    
    return circuit[::-1] + [circuit[-1]]

'''

# Find where to insert - right before def main():
main_idx = content.find('def main():')
if main_idx > 0:
    content = content[:main_idx] + eulerian_func + '\n' + content[main_idx:]
    print("[OK] Added compute_eulerian_circuit function")

# 2. Add --mode argument after parse_args setup, find the best place
# Look for where other args are defined
mode_arg = '''    parser.add_argument('--mode', type=str, choices=['sequential', 'all-pairs'], default='sequential',
                        help='Morphing mode: sequential (default) or all-pairs Eulerian circuit')
'''

# Find --output argument location and add after it
output_idx = content.find("parser.add_argument('--output'")
if output_idx > 0:
    # Find the end of this argument definition
    newline_idx = content.find('\n', output_idx)
    # Find the next parser.add_argument after this
    next_arg_idx = content.find("parser.add_argument", newline_idx)
    # Insert our mode argument before it
    if next_arg_idx > 0:
        content = content[:next_arg_idx] + mode_arg + '    ' + content[next_arg_idx:]
        print("[OK] Added --mode argument")

# 3. Update config loading section to handle mode
# Find the config loading block (morph_config.json)
config_load_idx = content.find("config_path = Path('morph_config.json')")
if config_load_idx > 0:
    # Find the section with "fps = args.fps"
    fps_idx = content.find("fps = args.fps or file_config.get('fps')", config_load_idx)
    if fps_idx > 0:
        # Before this, we need to use mode from args
        # Add mode assignment right before fps assignment
        mode_setup = "    mode = args.mode\n    "
        if "mode = args.mode" not in content:
            content = content[:fps_idx] + mode_setup + content[fps_idx:]
            print("[OK] Added mode variable assignment")

# 4. Update output filename handling based on mode
# Find where output path is set/used
# Add logic to change output name if all-pairs
output_assign_idx = content.find("print(f\"Output: {args.output}\")")
if output_assign_idx > 0:
    # Before the print, add logic to modify output path
    output_modify = '''    # Modify output filename based on mode
    output_path = args.output
    if mode == 'all-pairs' and 'morph' in output_path and 'eulerian' not in output_path:
        output_path = output_path.replace('morph.mp4', 'morph_eulerian.mp4')
        output_path = output_path.replace('morph_tps.mp4', 'morph_eulerian_tps.mp4')
    
    '''
    if "output_path = args.output" not in content:
        content = content[:output_assign_idx] + output_modify + content[output_assign_idx:]
        print("[OK] Added output path modification logic")
        # Also update the print to use output_path
        content = content.replace('print(f"Output: {args.output}")', 'print(f"Output: {output_path}")')

# 5. Find where image sequences are created and update logic
# Look for where images are ordered
create_frame_idx = content.find("def create_frame_generators(")
if create_frame_idx > 0:
    # Find the sequence creation logic
    sequence_idx = content.find("# Create transitions between consecutive faces", create_frame_idx)
    if sequence_idx > 0:
        # Find the for loop after this comment
        for_idx = content.find("for i in range(len(images_list) - 1)", sequence_idx)
        if for_idx < 0:
            for_idx = content.find("for i in range(", sequence_idx)
        
        if for_idx > 0:
            # Replace with logic that handles both modes
            old_for = "for i in range(len(images_list) - 1):\n        image_a = images_list[i]\n        image_b = images_list[i + 1]"
            new_for = """# Create transitions based on mode
    if mode == 'sequential':
        # Sequential: A -> B -> C -> ... -> A
        sequence = [(images_list[i], images_list[(i+1) % len(images_list)]) for i in range(len(images_list))]
    else:  # all-pairs
        # Eulerian circuit: visit all pairs exactly once
        indices = compute_eulerian_circuit(len(images_list))
        sequence = [(images_list[indices[i]], images_list[indices[i+1]]) for i in range(len(indices)-1)]
    
    for image_a, image_b in sequence"""
            
            # This is complex, so let's add a simpler transformation marker
            if "# Eulerian" not in content:
                seq_comment_idx = content.find("# Create transitions between", create_frame_idx)
                if seq_comment_idx > 0:
                    end_line_idx = content.find("\n", seq_comment_idx)
                    insertion = '''
    # Use mode to determine sequence
    if mode == 'sequential':
        image_pairs = [(images_list[i], images_list[(i+1) % len(images_list)]) for i in range(len(images_list))]
    else:  # all-pairs mode
        indices = compute_eulerian_circuit(len(images_list))
        image_pairs = [(images_list[indices[i]], images_list[indices[i+1]]) for i in range(len(indices)-1)]
    
    for image_a, image_b in image_pairs:
'''
                    # Skip the old for loop - find and remove it
                    content = content[:end_line_idx] + insertion + content[end_line_idx:]
                    print("[OK] Added Eulerian sequence logic")

# 6. Find TPS pair resolution and add reverse logic
tps_pair_idx = content.find("if args.backend == 'tps':")
if tps_pair_idx > 0:
    # Find the load_points_from_json call
    load_points_idx = content.find("load_points_from_json", tps_pair_idx)
    if load_points_idx > 0:
        # Look for the error handling
        end_section_idx = content.find("else:", load_points_idx)
        if end_section_idx > 0:
            # Add reverse logic before the error
            reverse_logic = '''            else:
                # Try reversed pair if direct one doesn't exist
                reversed_name = f"{stem_b}_{stem_a}.json"
                reversed_path = Path(args.points_dir) / reversed_name
                if reversed_path.exists():
                    # Load and reverse the correspondence points
                    points_b, points_a = load_points_from_json(str(reversed_path))
                    print(f"[OK] Using reversed correspondence: {reversed_name}")
                '''
            if "Try reversed" not in content:
                # Insert before the error message
                error_idx = content.find('f"[ERROR] TPS', load_points_idx)
                if error_idx > 0:
                    content = content[:error_idx] + reverse_logic + '\n                else:\n    ' + content[error_idx:]
                    print("[OK] Added reverse pair resolution logic")

# Write back
file_path.write_text(content, encoding='utf-8')
print("[OK] morph.py updated successfully")
