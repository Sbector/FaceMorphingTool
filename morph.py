"""
CLI entry point: high-quality face morphing orchestration.
Usage: python morph.py --photos photos/ --width 1080 --height 1920 --profile final
"""

import argparse
import sys
import json
from pathlib import Path
from itertools import chain
import cv2
import numpy as np

from detect import detect_landmarks_batch, validate_landmarks_quality, load_images_batch
from warp_tps import generate_morph_frames_tps, load_points_from_json
from video_writer import write_video


PROFILE_CONFIG = {
    'preview': {
        'fps': 24,
        'duration': 1.0,
        'hold': 0.5,
        'crf': 24,
        'preset': 'medium',
        'landmark_downscale': 2,  # Detect at 1/2 resolution for speed
    },
    'final': {
        'fps': 30,
        'duration': 2.0,
        'hold': 0.8,
        'crf': 18,
        'preset': 'slow',
        'landmark_downscale': 1,  # Detect at full resolution
    },
}


def compute_eulerian_circuit(n):
    """
    Compute an Eulerian circuit for complete graph K_n using Hierholzer's algorithm.
    
    Returns a list of n*(n-1)/2 + 1 vertex indices where first == last,
    representing a path that traverses all edges exactly once.
    
    Args:
        n: int, number of vertices (must be >= 1)
    
    Returns:
        list of vertex indices forming an Eulerian circuit
        
    Example: compute_eulerian_circuit(5) returns [0, 1, 2, 3, 4, 0, 2, 4, 1, 3, 0]
             (traverses all 10 edges of K_5, starts and ends at 0)
    """
    if n < 1:
        return [0]
    if n == 1:
        return [0, 0]
    
    # Build adjacency list for K_n (complete graph)
    # Each vertex connects to all others
    edges = {}
    for i in range(n):
        edges[i] = list(range(n))
        edges[i].remove(i)  # Remove self-loops
    
    # Hierholzer's algorithm to find Eulerian circuit
    stack = [0]
    path = []
    current_edges = {i: list(neighbors) for i, neighbors in edges.items()}
    
    while stack:
        v = stack[-1]
        if current_edges[v]:
            u = current_edges[v].pop()
            # Remove reverse edge to avoid traversing same edge twice
            current_edges[u].remove(v)
            stack.append(u)
        else:
            path.append(stack.pop())
    
    # Reverse to get the correct order
    circuit = path[::-1]
    
    # Ensure circuit starts and ends at same vertex
    if len(circuit) > 0 and circuit[0] != circuit[-1]:
        circuit.append(circuit[0])
    
    return circuit


def preserve_aspect_ratio(images_dict, landmarks_dict, target_width, target_height):
    """
    Normalize all images to target resolution while preserving aspect ratio.
    Uses letterboxing (black bars) if aspect ratios differ.
    
    Args:
        images_dict: {filename: image (BGR)}
        landmarks_dict: {filename: landmarks (N, 2)}
        target_width, target_height: output dimensions
    
    Returns:
        images_normalized, landmarks_normalized, (actual_w, actual_h, offset_x, offset_y)
    """
    images_normalized = {}
    landmarks_normalized = {}
    
    # Target aspect ratio
    target_ar = target_width / target_height
    
    # For simplicity, use first image as reference or compute mean
    sample_h, sample_w = list(images_dict.values())[0].shape[:2]
    sample_ar = sample_w / sample_h
    
    # If source AR matches target within ~5%, use direct stretch
    # Otherwise, letterbox to preserve face proportions
    if abs(sample_ar - target_ar) < 0.05:
        # Direct stretch acceptable
        use_letterbox = False
        actual_w, actual_h = target_width, target_height
        offset_x, offset_y = 0, 0
    else:
        # Use letterbox
        use_letterbox = True
        if sample_ar > target_ar:
            # Source is wider; fit to width
            actual_w = target_width
            actual_h = int(target_width / sample_ar)
        else:
            # Source is narrower; fit to height
            actual_h = target_height
            actual_w = int(target_height * sample_ar)
        offset_x = (target_width - actual_w) // 2
        offset_y = (target_height - actual_h) // 2
    
    for filename, image in images_dict.items():
        h_orig, w_orig = image.shape[:2]
        
        # Resize to actual dimensions
        image_resized = cv2.resize(image, (actual_w, actual_h))
        
        # Create canvas if letterbox
        if use_letterbox:
            canvas = np.zeros((target_height, target_width, 3), dtype=np.uint8)
            canvas[offset_y:offset_y+actual_h, offset_x:offset_x+actual_w] = image_resized
            images_normalized[filename] = canvas
        else:
            images_normalized[filename] = image_resized
        
        # Scale landmarks
        landmarks = landmarks_dict[filename].copy()
        scale_x = actual_w / w_orig
        scale_y = actual_h / h_orig
        landmarks[:, 0] = landmarks[:, 0] * scale_x + offset_x
        landmarks[:, 1] = landmarks[:, 1] * scale_y + offset_y
        landmarks_normalized[filename] = landmarks.astype('float32')
    
    return images_normalized, landmarks_normalized, (actual_w, actual_h, offset_x, offset_y)


def normalize_images(images_dict, landmarks_dict, target_size):
    """
    Normalize all images to same size and adjust landmarks accordingly.
    
    Args:
        images_dict: {filename: image}
        landmarks_dict: {filename: landmarks}
        target_size: tuple (width, height)
    
    Returns:
        images_normalized: {filename: resized image}
        landmarks_normalized: {filename: scaled landmarks}
    """
    images_normalized = {}
    landmarks_normalized = {}
    
    w_target, h_target = target_size
    
    for filename, image in images_dict.items():
        h_orig, w_orig = image.shape[:2]
        scale_x = w_target / w_orig
        scale_y = h_target / h_orig
        
        # Resize image
        image_resized = cv2.resize(image, (w_target, h_target))
        images_normalized[filename] = image_resized
        
        # Scale landmarks
        landmarks = landmarks_dict[filename].copy()
        landmarks[:, 0] *= scale_x
        landmarks[:, 1] *= scale_y
        landmarks_normalized[filename] = landmarks.astype('float32')
    
    return images_normalized, landmarks_normalized


def save_landmarks_cache(landmarks_dict, output_path):
    """Save landmarks to JSON cache for faster iteration."""
    cache_data = {}
    for filename, lm in landmarks_dict.items():
        cache_data[filename] = lm.tolist()
    
    with open(output_path, 'w') as f:
        json.dump(cache_data, f, indent=2)
    print(f"[OK] Landmarks cached to {output_path}")


def load_landmarks_cache(cache_path):
    """Load landmarks from cache if available."""
    if not Path(cache_path).exists():
        return None
    
    try:
        with open(cache_path, 'r') as f:
            cache_data = json.load(f)
        landmarks_dict = {k: np.array(v, dtype=np.float32) for k, v in cache_data.items()}
        print(f"[OK] Landmarks loaded from cache: {cache_path}")
        return landmarks_dict
    except Exception as e:
        print(f"[!] Cache load failed ({e}), will recompute")
        return None


def create_frame_generators(
    filenames, images, landmarks, fps, transition_duration, hold_duration,
    points_dir='landmarks',
    mode='sequential',
    eulerian_circuit=None
):
    """
    Create frame generators for each hold + transition pair.
    
    Args:
        filenames: list of str, filenames in order
        images: {filename: image}
        landmarks: {filename: landmarks}
        fps: int, frames per second
        transition_duration: float, seconds
        hold_duration: float, seconds
        backend: str, morphing backend ('delaunay', 'opticalflow', or 'tps')
        points_dir: str, directory containing TPS correspondence JSON files
        flow_attachment: float, TVL1 attachment parameter
        flow_tightness: float, TVL1 tightness parameter
        flow_max_disp: float or None, max flow displacement
        flow_smooth: int, flow smoothing kernel size
        flow_use_mask: bool, use face mask for optical flow
        mode: str, 'sequential' or 'all-pairs'
        eulerian_circuit: list of int, vertex indices for all-pairs mode
    
    Yields:
        Frame generators chained together
    """
    n_files = len(filenames)
    hold_frames = max(0, int(round(hold_duration * fps)))
    trans_frames = max(1, int(round(transition_duration * fps)))
    
    print(f"Frame counts: hold={hold_frames}, transition={trans_frames}")
    print(f"Points directory: {points_dir}\n")
    
    # TPS morphing function
    morph_func = generate_morph_frames_tps
    
    # Determine pairs based on mode
    if mode == 'all-pairs':
        if eulerian_circuit is None or len(eulerian_circuit) < 2:
            raise ValueError("all-pairs mode requires valid eulerian_circuit")
        # Create pairs from Eulerian circuit
        pairs = []
        for i in range(len(eulerian_circuit) - 1):
            idx_a = eulerian_circuit[i]
            idx_b = eulerian_circuit[i + 1]
            pairs.append((idx_a, idx_b))
    else:
        # Sequential mode: simple consecutive pairs
        pairs = []
        for i in range(n_files):
            pairs.append((i, (i + 1) % n_files))
    
    # Generate frames for each pair
    for pair_idx, (idx_current, idx_next) in enumerate(pairs):
        current_file = filenames[idx_current]
        next_file = filenames[idx_next]
        
        img_current = images[current_file]
        lm_current = landmarks[current_file]
        
        img_next = images[next_file]
        lm_next = landmarks[next_file]
        
        # Emit hold frames (static) - only for first occurrence of each image in sequence
        is_first_occurrence = False
        if eulerian_circuit is None:
            # Sequential mode: first occurrence is when pair_idx == 0
            is_first_occurrence = (pair_idx == 0)
        else:
            # Eulerian mode: check if this image's first appearance in circuit
            is_first_occurrence = (pair_idx == 0 or eulerian_circuit[pair_idx] != eulerian_circuit[pair_idx - 1])
        
        if hold_frames > 0 and is_first_occurrence:
            print(f"Hold frame: {current_file}")
            for _ in range(hold_frames):
                yield img_current
        
        # Emit transition frames (morphing)
        print(f"Morph {current_file} -> {next_file} ({trans_frames} frames)")
        
        # TPS with correspondence points from JSON
        stem_current = Path(current_file).stem
        stem_next = Path(next_file).stem
        
        # Try to load correspondence points with fallback
        json_path = Path(points_dir) / f"{stem_current}_{stem_next}.json"
        json_path_rev = Path(points_dir) / f"{stem_next}_{stem_current}.json"
        
        pts_a = None
        pts_b = None
        
        if json_path.exists():
            pts_a, pts_b = load_points_from_json(str(json_path))
            print(f"  Loaded correspondence from {json_path.name}")
        elif json_path_rev.exists():
            pts_a, pts_b = load_points_from_json(str(json_path_rev))
            # Reverse the points since we loaded them backwards
            pts_a, pts_b = pts_b, pts_a
            print(f"  Loaded reversed correspondence from {json_path_rev.name}")
        else:
            raise FileNotFoundError(
                f"Correspondence points not found: {json_path} or {json_path_rev}\n"
                f"Run: python landmark_editor.py --image-a {current_file} --image-b {next_file}"
            )
        
        for frame in morph_func(img_current, img_next, pts_a, pts_b, trans_frames):
            yield frame


def main():
    parser = argparse.ArgumentParser(
        description='High-quality face morphing video generator for portrait sequences',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick preview (low res, fast)
  python morph.py --photos photos/ --width 1080 --height 1920 --profile preview
  
  # High-quality final (full res, slow)
  python morph.py --photos photos/ --width 1080 --height 1920 --profile final
  
  # Custom params
  python morph.py --photos photos/ --width 1080 --height 1920 \\
    --fps 30 --duration 2.5 --hold 1.0 --crf 17 --preset slow
        """
    )
    
    # Paths
    parser.add_argument('--photos', type=str, default='photos/',
                        help='Directory with portrait images')
    parser.add_argument('--output', type=str, default='output/morph.mp4',
                        help='Output MP4 path')
    
    # Resolution
    parser.add_argument('--width', type=int, default=1080,
                        help='Output width (pixels)')
    parser.add_argument('--height', type=int, default=1920,
                        help='Output height (pixels)')
    
    # Profile (preset)
    parser.add_argument('--profile', type=str, choices=['preview', 'final'], default='preview',
                        help='Render profile: preview (fast) or final (quality)')
    
    # Backend
    # TPS is the only supported backend now
    parser.add_argument('--points-dir', type=str, default='landmarks',
                        help='Directory containing correspondence JSON files for TPS backend')
    
    # Animation
    parser.add_argument('--fps', type=int, default=None,
                        help='Frames per second')
    parser.add_argument('--duration', type=float, default=None,
                        help='Transition duration (seconds)')
    parser.add_argument('--hold', type=float, default=None,
                        help='Hold time per face (seconds)')
    
    # Quality
    parser.add_argument('--crf', type=int, default=None,
                        help='H.264 CRF (0-51; lower-better; default 18-24)')
    parser.add_argument('--preset', type=str, 
                        choices=['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 
                                 'medium', 'slow', 'slower', 'veryslow'],
                        default=None, help='H.264 encoding preset')
    
    # Order & cache
    parser.add_argument('--order', type=str, default=None,
                        help='Comma-separated image order override')
    parser.add_argument('--cache-landmarks', action='store_true',
                        help='Save landmarks to cache after detection')
    parser.add_argument('--use-cache', action='store_true',
                        help='Load landmarks from cache if available')
    
    # Morphing sequence mode
    parser.add_argument('--mode', type=str, choices=['sequential', 'all-pairs'], default='sequential',
                        help='Morphing sequence: sequential (img[0]->img[1]->...) or all-pairs (Eulerian circuit)')
    
    args = parser.parse_args()
    
    # Apply profile defaults
    profile = PROFILE_CONFIG[args.profile]
    
    # Load morph_config.json if it exists (prioridad: CLI > config file > profile)
    config_path = Path('morph_config.json')
    file_config = {}
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                file_config = json.load(f)
            print(f"[OK] Loaded timing config from {config_path}")
        except Exception as e:
            print(f"[!] Warning: Failed to load {config_path}: {e}")
    
    # Resolve parameter values with priority: CLI > config file > profile
    fps = args.fps or file_config.get('fps') or profile['fps']
    duration = args.duration or file_config.get('duration') or profile['duration']
    hold = args.hold or file_config.get('hold') or profile['hold']
    crf = args.crf or profile['crf']
    preset = args.preset or profile['preset']
    landmark_downscale = profile['landmark_downscale']
    
    # Validate resolution
    if args.width <= 0 or args.height <= 0:
        print("Error: width and height must be positive")
        return 1
    
    photo_dir = Path(args.photos)
    if not photo_dir.exists():
        print(f"Error: Photo directory not found: {photo_dir}")
        return 1
    
    # Generate output path dynamically based on mode
    output_base = args.output if args.output != 'output/morph.mp4' else None
    if output_base is None:
        # Use default with mode suffix (TPS is implicit)
        mode_suffix = '_eulerian' if args.mode == 'all-pairs' else ''
        output_path = Path(f"output/morph{mode_suffix}.mp4")
    else:
        # User provided custom output path
        if args.mode == 'all-pairs':
            # Modify filename if it matches standard patterns
            output_str = str(output_base)
            if output_str.endswith('morph.mp4'):
                output_str = output_str.replace('morph.mp4', 'morph_eulerian.mp4')
            elif output_str.endswith('.mp4'):
                output_str = output_str.replace('.mp4', '_eulerian.mp4')
            output_path = Path(output_str)
        else:
            output_path = Path(output_base)
    
    try:
        print(f"Face Morpher - TPS backend, {args.profile.upper()} profile")
        print(f"Mode: {args.mode}")
        print(f"Output: {args.width}x{args.height} @ {fps} fps")
        print(f"Encoding: CRF {crf}, preset {preset}\n")
        
        # Try to load landmarks from cache
        landmarks_dict = None
        cache_path = photo_dir / '.landmarks_cache.json'
        if args.use_cache:
            landmarks_dict = load_landmarks_cache(cache_path)
        
        # Detect landmarks if not cached
        if landmarks_dict is None:
            print(f"Loading images from {photo_dir}...")
            landmarks_dict, images_dict, filenames = detect_landmarks_batch(
                photo_dir,
                downscale=landmark_downscale
            )
            
            # Validate landmark quality
            print("\nValidating landmarks...")
            for filename in filenames:
                quality_score = validate_landmarks_quality(images_dict[filename], landmarks_dict[filename])
                print(f"  {filename}: quality score {quality_score:.2f}")
            
            # Cache if requested
            if args.cache_landmarks:
                save_landmarks_cache(landmarks_dict, cache_path)
        else:
            # Load images only
            print(f"Loading images from {photo_dir}...")
            images_dict, filenames = load_images_batch(photo_dir)
        
        # Override order if specified
        if args.order:
            requested_order = [f.strip() for f in args.order.split(',')]
            filenames = requested_order
        
        print(f"Loaded {len(filenames)} images: {', '.join(filenames)}\n")
        
        # Compute Eulerian circuit if using all-pairs mode
        eulerian_circuit = None
        if args.mode == 'all-pairs':
            n = len(filenames)
            eulerian_circuit = compute_eulerian_circuit(n)
            print(f"Computed Eulerian circuit for K_{n}: {eulerian_circuit}")
            print(f"Circuit length: {len(eulerian_circuit) - 1} edges\n")
        
        # Normalize images + landmarks to target resolution
        print(f"Normalizing to {args.width}x{args.height} (aspect ratio preserved)...")
        images_norm, landmarks_norm, (actual_w, actual_h, offset_x, offset_y) = preserve_aspect_ratio(
            images_dict, landmarks_dict, args.width, args.height
        )
        print(f"Actual canvas: {actual_w}x{actual_h} at ({offset_x}, {offset_y})\n")
        
        # Generate video
        frame_gen = create_frame_generators(
            filenames, images_norm, landmarks_norm,
            fps=fps, transition_duration=duration, hold_duration=hold,
            points_dir=args.points_dir,
            mode=args.mode,
            eulerian_circuit=eulerian_circuit
        )
        
        write_video(
            output_path,
            frame_gen,
            size=(args.width, args.height),
            fps=fps,
            crf=crf,
            preset=preset
        )
        
        print(f"\n[OK] Success! Video saved to {output_path}")
        print(f"Profile: {args.profile} | Resolution: {args.width}x{args.height} | " \
              f"Duration calc: {len(filenames)} images | Mode: {args.mode}")
        return 0
        
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
