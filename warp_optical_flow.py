"""
Optical Flow backend for morphing via scikit-image TVL1.
Includes flow clipping, smoothing, and face mask stabilization for better results.
"""

import cv2
import numpy as np

try:
    from skimage.registration import optical_flow_tvl1
    HAS_SKIMAGE = True
except ImportError:
    HAS_SKIMAGE = False


def create_face_mask(landmarks, h, w, feather_radius=30):
    """
    Create a binary mask of the face region from landmarks.
    Used to stabilize background and neck during morphing.
    
    Args:
        landmarks: np.array (N, 2), facial landmarks
        h, w: int, image height and width
        feather_radius: int, pixels to feather the mask edge
    
    Returns:
        mask: np.float32, values in [0, 1], 1 = face, 0 = background
    """
    mask = np.zeros((h, w), dtype=np.float32)
    
    # Use landmarks to define face region (convex hull + extra boundary)
    if len(landmarks) > 0:
        hull = cv2.convexHull(landmarks.astype(np.int32))
        cv2.drawContours(mask, [hull], 0, 1.0, -1)
        
        # Feather the edges for smooth blending
        if feather_radius > 0:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (feather_radius*2, feather_radius*2))
            # Dilate to expand face region slightly
            mask = cv2.dilate(mask, kernel, iterations=1)
            # Gaussian blur to create smooth feathering
            mask = cv2.GaussianBlur(mask, (feather_radius*2+1, feather_radius*2+1), feather_radius // 2)
            mask = np.clip(mask, 0, 1)
    
    return mask


def clip_and_smooth_flow(flow, max_displacement=None, smooth_kernel=5):
    """
    Clip flow magnitude and optionally smooth the field to avoid extreme deformations.
    
    Args:
        flow: np.array (H, W, 2), optical flow field [dy, dx]
        max_displacement: float or None, max allowed magnitude per pixel. If None, auto-compute as 0.1*min(H,W)
        smooth_kernel: int, kernel size for filtering (odd number, 1=no smoothing)
    
    Returns:
        flow_clipped: np.array (H, W, 2), clipped and smoothed flow
    """
    h, w = flow.shape[:2]
    
    # Auto-compute max displacement if not provided
    if max_displacement is None:
        max_displacement = min(h, w) * 0.1
    
    # Clip flow magnitude
    magnitude = np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)
    magnitude = np.clip(magnitude, 0, max_displacement)
    
    # Renormalize clipped flow
    magnitude_orig = np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)
    mask_nonzero = magnitude_orig > 0
    flow_clipped = flow.copy()
    
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = magnitude / magnitude_orig
        ratio = np.where(mask_nonzero, ratio, 1.0)
        flow_clipped[..., 0] *= ratio
        flow_clipped[..., 1] *= ratio
    
    # Smooth flow field with Gaussian blur (works with float32)
    if smooth_kernel > 1:
        # Ensure kernel is odd
        if smooth_kernel % 2 == 0:
            smooth_kernel += 1
        flow_clipped[..., 0] = cv2.GaussianBlur(flow_clipped[..., 0], (smooth_kernel, smooth_kernel), smooth_kernel // 3)
        flow_clipped[..., 1] = cv2.GaussianBlur(flow_clipped[..., 1], (smooth_kernel, smooth_kernel), smooth_kernel // 3)
    
    return flow_clipped


def generate_morph_frames_optical_flow(
    img_a, img_b, num_frames,
    landmarks_a=None, landmarks_b=None,
    attachment=15, tightness=0.3,
    max_displacement=None, smooth_kernel=5,
    use_face_mask=True
):
    """
    Generate morphed frames using dense optical flow interpolation with improvements.
    
    Args:
        img_a: np.uint8 BGR source image
        img_b: np.uint8 BGR target image
        num_frames: int, number of frames to generate
        landmarks_a: np.array (N, 2) or None, source landmarks (used for face mask)
        landmarks_b: np.array (N, 2) or None, target landmarks (used for face mask)
        attachment: float, TVL1 attachment parameter (higher = stronger data fidelity)
        tightness: float, TVL1 tightness parameter (higher = more regularization)
        max_displacement: float or None, max flow magnitude. If None, auto-compute
        smooth_kernel: int, median filter kernel for flow smoothing
        use_face_mask: bool, whether to stabilize background using face mask
    
    Yields:
        frame: np.uint8 BGR morphed frame
    """
    if not HAS_SKIMAGE:
        raise ImportError("scikit-image required. Install with: pip install scikit-image")
    
    if img_a.shape != img_b.shape:
        raise ValueError(f"Image shapes don't match: {img_a.shape} vs {img_b.shape}")
    
    h, w = img_a.shape[:2]
    
    print(f"Morphing with Optical Flow (attachment={attachment}, tightness={tightness}, " \
          f"max_disp={max_displacement or 'auto'}, kernel={smooth_kernel}) — {num_frames} frames")
    
    # Convert to grayscale for optical flow
    img_a_gray = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    img_b_gray = cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    
    # Pre-compute optical flows with custom parameters
    flow_a_to_b = optical_flow_tvl1(img_a_gray, img_b_gray, attachment=attachment, tightness=tightness)
    flow_b_to_a = optical_flow_tvl1(img_b_gray, img_a_gray, attachment=attachment, tightness=tightness)
    
    # Clip and smooth flows
    flow_a_to_b = clip_and_smooth_flow(flow_a_to_b, max_displacement, smooth_kernel)
    flow_b_to_a = clip_and_smooth_flow(flow_b_to_a, max_displacement, smooth_kernel)
    
    # Create face masks if landmarks provided
    mask_a = None
    mask_b = None
    if use_face_mask and landmarks_a is not None:
        mask_a = create_face_mask(landmarks_a, h, w)
    if use_face_mask and landmarks_b is not None:
        mask_b = create_face_mask(landmarks_b, h, w)
    
    # Average masks if both available
    face_mask = None
    if mask_a is not None and mask_b is not None:
        face_mask = (mask_a + mask_b) * 0.5
    elif mask_a is not None:
        face_mask = mask_a
    elif mask_b is not None:
        face_mask = mask_b
    
    yy, xx = np.meshgrid(np.arange(h, dtype=np.float32), np.arange(w, dtype=np.float32), indexing='ij')
    
    for i in range(num_frames):
        t = i / max(1, num_frames - 1)
        t_eased = 3 * t**2 - 2 * t**3  # smoothstep easing
        
        # Warp A towards B using forward flow, B towards A using backward flow
        # At t=0: A stays, B fully warped towards A; at t=1: A fully warped towards B, B stays
        map_x_a = (xx + t * flow_a_to_b[1]).astype(np.float32)
        map_y_a = (yy + t * flow_a_to_b[0]).astype(np.float32)
        map_x_b = (xx + (1 - t) * flow_b_to_a[1]).astype(np.float32)
        map_y_b = (yy + (1 - t) * flow_b_to_a[0]).astype(np.float32)
        
        warped_a = cv2.remap(img_a, map_x_a, map_y_a, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
        warped_b = cv2.remap(img_b, map_x_b, map_y_b, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
        
        # Blend warped images
        frame = ((1 - t_eased) * warped_a.astype(np.float32) + 
                 t_eased * warped_b.astype(np.float32))
        
        # Apply face mask to stabilize background (optional)
        if face_mask is not None:
            # Blend face region only; keep background from A or B (crossfade)
            bg_frame = ((1 - t_eased) * img_a.astype(np.float32) + 
                       t_eased * img_b.astype(np.float32))
            
            # Expand mask to 3D for RGB blending
            face_mask_3d = np.stack([face_mask]*3, axis=-1)
            frame = frame * face_mask_3d + bg_frame * (1 - face_mask_3d)
        
        yield np.clip(frame, 0, 255).astype(np.uint8)
