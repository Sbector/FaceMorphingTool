"""
Delaunay-based morphing: vectorized displacement field + cv2.remap.
Orders of magnitude faster than per-triangle warping.
"""

import cv2
import numpy as np


def smoothstep(t):
    """Smooth easing curve: 3t²-2t³. Maps [0,1] → [0,1] smoothly."""
    return 3 * t**2 - 2 * t**3


def interpolate_landmarks(landmarks_a, landmarks_b, t):
    """
    Interpolate between two landmark arrays using smoothstep easing.
    
    Args:
        landmarks_a: np.array (N, 2)
        landmarks_b: np.array (N, 2)
        t: float in [0, 1], raw interpolation parameter
    
    Returns:
        landmarks_interp: np.array (N, 2) interpolated landmarks
        t_eased: float, the eased t value for per-triangle blending
    """
    t_eased = smoothstep(t)
    landmarks_interp = (1 - t_eased) * landmarks_a + t_eased * landmarks_b
    return landmarks_interp.astype(np.float32), t_eased


def build_delaunay_triangulation(landmarks, image_shape):
    """
    Build Delaunay triangulation from landmark points.
    
    Args:
        landmarks: np.array (N, 2) of vertex positions
        image_shape: tuple (height, width) for canvas bounds
    
    Returns:
        triangles: list of lists, each [idx_a, idx_b, idx_c] into landmarks array
    """
    h, w = image_shape[:2]
    rect = (0, 0, w, h)
    
    subdiv = cv2.Subdiv2D(rect)
    for i, (x, y) in enumerate(landmarks):
        subdiv.insert((float(x), float(y)))
    
    triangles_raw = subdiv.getTriangleList()
    
    # Resolve floating-point vertex indices back to landmark indices
    # Use rounded lookup dict to handle numerical drift
    landmark_dict = {}
    for i, (x, y) in enumerate(landmarks):
        key = (round(x, 1), round(y, 1))
        landmark_dict[key] = i
    
    triangles = []
    for tri in triangles_raw:
        # tri is [x0, y0, x1, y1, x2, y2, ...]
        pts = [(tri[i], tri[i+1]) for i in range(0, 6, 2)]
        indices = []
        for x, y in pts:
            key = (round(x, 1), round(y, 1))
            if key in landmark_dict:
                indices.append(landmark_dict[key])
        
        if len(indices) == 3 and len(set(indices)) == 3:  # Valid unique triangle
            triangles.append(indices)
    
    return triangles


def barycentric_coords(p, a, b, c):
    """
    Compute barycentric coordinates of point p w.r.t. triangle (a, b, c).
    Returns (u, v, w) where p = u*a + v*b + w*c and u+v+w=1.
    Also returns a boolean: True if point is inside triangle, False otherwise.
    """
    v0 = c - a
    v1 = b - a
    v2 = p - a
    
    dot00 = np.dot(v0, v0)
    dot01 = np.dot(v0, v1)
    dot02 = np.dot(v0, v2)
    dot11 = np.dot(v1, v1)
    dot12 = np.dot(v1, v2)
    
    inv_denom = 1.0 / (dot00 * dot11 - dot01 * dot01 + 1e-10)
    u = (dot11 * dot02 - dot01 * dot12) * inv_denom
    v = (dot00 * dot12 - dot01 * dot02) * inv_denom
    w = 1.0 - u - v
    
    inside = (u >= -0.001) and (v >= -0.001) and (w >= -0.001)
    return u, v, w, inside


def _to_python_int(val):
    """Convert numpy scalar or Python number to Python int."""
    if isinstance(val, np.ndarray):
        val = float(val.flat[0])  # Extract single element
    return int(val)


def build_displacement_map(landmarks_src, landmarks_dst, landmarks_interp, triangles, shape):
    """
    Build a dense displacement map from src to dst using Delaunay triangulation.
    
    For each pixel in the image, determine which triangle contains it, then use
    affine transformation to map it back to the source image.
    
    Args:
        landmarks_src: np.array (N, 2) source landmarks
        landmarks_dst: np.array (N, 2) destination landmarks  
        landmarks_interp: np.array (N, 2) interpolated landmarks (for spatial queries)
        triangles: list of [idx_a, idx_b, idx_c] triangle indices
        shape: tuple (H, W) image shape
    
    Returns:
        map_x: float32 array (H, W) x-coordinates in source space
        map_y: float32 array (H, W) y-coordinates in source space
    """
    # Validate inputs before unpacking
    assert isinstance(shape, (tuple, list)), f"shape must be tuple/list, got {type(shape)}"
    assert len(shape) == 2, f"shape must have 2 elements, got {len(shape)}"
    
    h, w = shape
    
    map_x = np.zeros((h, w), dtype=np.float32)
    map_y = np.zeros((h, w), dtype=np.float32)
    coverage = np.zeros((h, w), dtype=np.uint8)
    
    # For each triangle
    for tri_idx_list in triangles:
        tri_idx = np.array(tri_idx_list)  # Convert to numpy array for fancy indexing
        
        # Get triangle vertices at each stage (fancy indexing returns shape (3, 2))
        src_tri = landmarks_src[tri_idx].astype(np.float32)
        dst_tri = landmarks_dst[tri_idx].astype(np.float32)
        interp_tri = landmarks_interp[tri_idx].astype(np.float32)
        
        # Get bounding box in interpolated (query) space (clip to image bounds)
        min_x_float = float(np.min(interp_tri[:, 0]))
        max_x_float = float(np.max(interp_tri[:, 0]))
        min_y_float = float(np.min(interp_tri[:, 1]))
        max_y_float = float(np.max(interp_tri[:, 1]))
        
        # DEBUG
        # print(f"DEBUG: min_x_float={min_x_float}, type={type(min_x_float)}")
        # print(f"DEBUG: h={h}, w={w}, type(h)={type(h)}, type(w)={type(w)}")
        
        min_x = max(0, int(min_x_float))
        max_x = min(w - 1, int(max_x_float) + 2)
        
        min_y = max(0, int(min_y_float))
        max_y = min(h - 1, int(max_y_float) + 2)
        
        if max_x <= min_x or max_y <= min_y:
            continue
        
        # Create grid of points in destination (interpolated) space
        yy, xx = np.meshgrid(np.arange(min_y, max_y, dtype=np.float32),
                             np.arange(min_x, max_x, dtype=np.float32),
                             indexing='ij')
        pts = np.stack([xx, yy], axis=-1)  # (height, width, 2)
        
        # Compute barycentric coordinates w.r.t. interpolated triangle
        # For each pixel, check if it's inside the triangle
        v0 = interp_tri[2] - interp_tri[0]  # (2,)
        v1 = interp_tri[1] - interp_tri[0]  # (2,)
        v2 = pts - interp_tri[0]  # (height, width, 2)
        
        dot00 = np.dot(v0, v0)  # scalar
        dot01 = np.dot(v0, v1)  # scalar
        dot02 = np.dot(v2, v0)  # (height, width) — each pixel's dot product
        dot11 = np.dot(v1, v1)  # scalar
        dot12 = np.dot(v2, v1)  # (height, width) — each pixel's dot product
        
        inv_denom = 1.0 / (dot00 * dot11 - dot01 * dot01 + 1e-10)
        u = (dot11 * dot02 - dot01 * dot12) * inv_denom
        v = (dot00 * dot12 - dot01 * dot02) * inv_denom
        bary_w = 1.0 - u - v
        
        inside = (u >= -0.001) & (v >= -0.001) & (bary_w >= -0.001)
        
        # For pixels inside triangle, compute corresponding position in source space
        # Using affine transform from src to dst
        src_pt0 = src_tri[0]
        dst_pt0 = dst_tri[0]
        src_v1 = src_tri[1] - src_tri[0]
        src_v2 = src_tri[2] - src_tri[0]
        
        # Map from dst space back to src space
        src_x_mapped = src_pt0[0] + u * src_v1[0] + v * src_v2[0]
        src_y_mapped = src_pt0[1] + u * src_v1[1] + v * src_v2[1]
        
        # Write to map for pixels inside triangle (no overlap handling needed, first write wins)
        map_x[min_y:max_y, min_x:max_x][inside] = src_x_mapped[inside]
        map_y[min_y:max_y, min_x:max_x][inside] = src_y_mapped[inside]
        coverage[min_y:max_y, min_x:max_x][inside] = 1
    
    # For pixels not covered by any triangle, use identity mapping (nearest pixel)
    uncovered = coverage == 0
    if np.any(uncovered):
        yy_full, xx_full = np.meshgrid(np.arange(h, dtype=np.float32),
                                       np.arange(w, dtype=np.float32),
                                       indexing='ij')
        map_x[uncovered] = xx_full[uncovered]
        map_y[uncovered] = yy_full[uncovered]
    
    return map_x, map_y


def morph_frame(img_a, landmarks_a, img_b, landmarks_b, t, triangles):
    """
    Generate a single morphed frame between two images using displacement fields.
    
    Args:
        img_a: np.uint8 BGR source image
        landmarks_a: np.array (N, 2) source landmarks
        img_b: np.uint8 BGR target image
        landmarks_b: np.array (N, 2) target landmarks
        t: float in [0, 1], interpolation parameter
        triangles: list of [idx_a, idx_b, idx_c] triangle indices
    
    Returns:
        frame: np.uint8 BGR morphed frame, same shape as img_a
    """
    h, w = img_a.shape[:2]
    
    # Interpolate landmarks
    landmarks_t, t_eased = interpolate_landmarks(landmarks_a, landmarks_b, t)
    
    # Build displacement maps: where each pixel in the morphed image comes from in A and B
    map_x_a, map_y_a = build_displacement_map(landmarks_a, landmarks_t, landmarks_t, triangles, (h, w))
    map_x_b, map_y_b = build_displacement_map(landmarks_b, landmarks_t, landmarks_t, triangles, (h, w))
    
    # Remap images using displacement fields (vectorized, ~1000x faster than per-triangle)
    warped_a = cv2.remap(img_a, map_x_a, map_y_a, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
    warped_b = cv2.remap(img_b, map_x_b, map_y_b, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
    
    # Blend between warped images
    frame = ((1 - t_eased) * warped_a.astype(np.float32) + 
             t_eased * warped_b.astype(np.float32))
    
    return np.clip(frame, 0, 255).astype(np.uint8)


def generate_morph_frames(img_a, landmarks_a, img_b, landmarks_b, num_frames):
    """
    Generate a sequence of morphed frames from image A to image B.
    
    Args:
        img_a: np.uint8 BGR source image
        landmarks_a: np.array (N, 2)
        img_b: np.uint8 BGR target image
        landmarks_b: np.array (N, 2)
        num_frames: int, number of frames to generate (inclusive of endpoints)
    
    Yields:
        frame: np.uint8 BGR morphed frame
    """
    # Ensure same image shape
    if img_a.shape != img_b.shape:
        raise ValueError(f"Image shapes don't match: {img_a.shape} vs {img_b.shape}")
    
    if landmarks_a.shape != landmarks_b.shape:
        raise ValueError(f"Landmark shapes don't match: {landmarks_a.shape} vs {landmarks_b.shape}")
    
    # Build triangulation once from intermediate landmarks
    landmarks_mid = (landmarks_a + landmarks_b) / 2.0
    triangles = build_delaunay_triangulation(landmarks_mid, img_a.shape)
    
    if not triangles:
        raise ValueError("Failed to build Delaunay triangulation")
    
    print(f"Triangulation: {len(triangles)} triangles")
    
    for i in range(num_frames):
        t = i / max(1, num_frames - 1)  # [0, 1]
        frame = morph_frame(img_a, landmarks_a, img_b, landmarks_b, t, triangles)
        yield frame

