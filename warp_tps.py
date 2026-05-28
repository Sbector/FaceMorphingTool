"""
Thin Plate Spline (TPS) morphing backend guided by manual correspondence points.
Uses scipy's RBFInterpolator with TPS kernel for smooth, natural warp.
"""

import cv2
import json
import numpy as np
from pathlib import Path
from scipy.interpolate import RBFInterpolator


def load_points_from_json(json_path):
    """
    Load correspondence points from JSON file created by landmark_editor.py.
    
    Args:
        json_path: str or Path, path to JSON file with correspondence data
    
    Returns:
        points_a: np.array (N, 2) in [x, y] format for source image
        points_b: np.array (N, 2) in [x, y] format for target image
    """
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    pairs = data['pairs']
    points_a = np.array([[p['a'][0], p['a'][1]] for p in pairs], dtype=np.float32)
    points_b = np.array([[p['b'][0], p['b'][1]] for p in pairs], dtype=np.float32)
    
    return points_a, points_b


def add_boundary_anchors(points_a, points_b, image_h, image_w):
    """
    Add boundary anchor points to prevent background deformation.
    These points map to themselves, constraining the border region.
    
    Args:
        points_a: np.array (N, 2) correspondence points in A
        points_b: np.array (N, 2) correspondence points in B
        image_h, image_w: int, image dimensions
    
    Returns:
        points_a_aug: np.array (N+8, 2) with boundary anchors
        points_b_aug: np.array (N+8, 2) with boundary anchors
    """
    # 8 boundary points: corners + midpoints of edges
    boundary_points = np.array([
        [0, 0],                    # top-left
        [image_w // 2, 0],         # top-center
        [image_w - 1, 0],          # top-right
        [image_w - 1, image_h // 2],  # right-center
        [image_w - 1, image_h - 1],   # bottom-right
        [image_w // 2, image_h - 1],  # bottom-center
        [0, image_h - 1],          # bottom-left
        [0, image_h // 2],         # left-center
    ], dtype=np.float32)
    
    # Boundary points map to themselves for both A and B (stabilize background)
    points_a_aug = np.vstack([points_a, boundary_points])
    points_b_aug = np.vstack([points_b, boundary_points])
    
    return points_a_aug, points_b_aug


def precompute_tps_warp_fields(img_shape, points_a, points_b):
    """
    Precompute full displacement fields using TPS for efficiency.
    Evaluates RBF once over the entire grid (expensive) but interpolation per frame is cheap.
    
    Args:
        img_shape: tuple (height, width)
        points_a: np.array (N, 2) correspondence points in A
        points_b: np.array (N, 2) correspondence points in B
    
    Returns:
        map_x_a: np.array (H, W) float32, x-coordinates to sample from A in dest space
        map_y_a: np.array (H, W) float32, y-coordinates to sample from A in dest space
        map_x_b: np.array (H, W) float32, x-coordinates to sample from B in dest space
        map_y_b: np.array (H, W) float32, y-coordinates to sample from B in dest space
    """
    h, w = img_shape
    
    # Add boundary anchors to stabilize edges
    points_a_aug, points_b_aug = add_boundary_anchors(points_a, points_b, h, w)
    
    print(f"TPS: Building warp fields with {len(points_a_aug)} points (including {8} boundary anchors)")
    
    # Build RBF interpolators
    # rbf_a maps from destination space (B) to source space (A) for sampling
    rbf_a = RBFInterpolator(points_b_aug, points_a_aug, kernel='thin_plate_spline', smoothing=1e-6)
    # rbf_b maps from destination space (A) to source space (B) for sampling
    rbf_b = RBFInterpolator(points_a_aug, points_b_aug, kernel='thin_plate_spline', smoothing=1e-6)
    
    # Create grid in output space
    yy, xx = np.meshgrid(np.arange(h, dtype=np.float32), np.arange(w, dtype=np.float32), indexing='ij')
    grid_xy = np.column_stack([xx.ravel(), yy.ravel()])  # (H*W, 2) in [x, y] format
    
    print(f"TPS: Evaluating RBF on {h}x{w} grid ({h*w} points)...")
    
    # Evaluate RBFs to get source coordinates for remapping
    sampled_a = rbf_a(grid_xy).reshape(h, w, 2)
    map_x_a = sampled_a[:, :, 0].astype(np.float32)
    map_y_a = sampled_a[:, :, 1].astype(np.float32)
    
    sampled_b = rbf_b(grid_xy).reshape(h, w, 2)
    map_x_b = sampled_b[:, :, 0].astype(np.float32)
    map_y_b = sampled_b[:, :, 1].astype(np.float32)
    
    print(f"TPS: Warp fields ready")
    
    return map_x_a, map_y_a, map_x_b, map_y_b


def generate_morph_frames_tps(img_a, img_b, points_a, points_b, num_frames):
    """
    Generate morphed frames using Thin Plate Spline warp guided by correspondence points.
    
    TPS produces a smooth, mathematically-constrained deformation field that minimizes
    bending energy while respecting the correspondence constraints.
    
    Args:
        img_a: np.uint8 BGR source image
        img_b: np.uint8 BGR target image
        points_a: np.array (N, 2) correspondence points in A [x, y] format
        points_b: np.array (N, 2) correspondence points in B [x, y] format
        num_frames: int, number of frames to generate (including t=0 and t=1)
    
    Yields:
        frame: np.uint8 BGR morphed frame at parameter t ∈ [0, 1]
    """
    if img_a.shape != img_b.shape:
        raise ValueError(f"Image shapes don't match: {img_a.shape} vs {img_b.shape}")
    
    if points_a.shape != points_b.shape or len(points_a.shape) != 2 or points_a.shape[1] != 2:
        raise ValueError(f"Points shapes invalid: A {points_a.shape}, B {points_b.shape} (both should be N×2)")
    
    h, w = img_a.shape[:2]
    
    print(f"Morphing with TPS backend ({num_frames} frames, {len(points_a)} correspondence points)")
    
    # Precompute warp fields (expensive, done once)
    map_x_a_full, map_y_a_full, map_x_b_full, map_y_b_full = precompute_tps_warp_fields(
        (h, w), points_a, points_b
    )
    
    # Identity maps for t=0 and t=1
    yy, xx = np.meshgrid(np.arange(h, dtype=np.float32), np.arange(w, dtype=np.float32), indexing='ij')
    
    for i in range(num_frames):
        t = i / max(1, num_frames - 1)
        t_eased = 3 * t**2 - 2 * t**3  # smoothstep easing
        
        # Interpolate warp fields linearly
        # A warped towards B: at t=0 stays put, at t=1 fully warped to B space
        map_x_a = (1 - t) * xx + t * map_x_a_full
        map_y_a = (1 - t) * yy + t * map_y_a_full
        
        # B warped towards A: at t=0 fully warped to A space, at t=1 stays put
        map_x_b = t * xx + (1 - t) * map_x_b_full
        map_y_b = t * yy + (1 - t) * map_y_b_full
        
        # Remap images
        warped_a = cv2.remap(img_a, map_x_a.astype(np.float32), map_y_a.astype(np.float32),
                             cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
        warped_b = cv2.remap(img_b, map_x_b.astype(np.float32), map_y_b.astype(np.float32),
                             cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
        
        # Blend
        frame = ((1 - t_eased) * warped_a.astype(np.float32) + 
                 t_eased * warped_b.astype(np.float32))
        
        yield np.clip(frame, 0, 255).astype(np.uint8)
