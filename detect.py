"""
Landmark detection using MediaPipe FaceMesh.
Returns 468 face mesh landmarks + 8 boundary anchor points = 476 total.
"""

import cv2
import numpy as np
import mediapipe as mp
from pathlib import Path


def detect_landmarks(image_path, downscale=1, target_size=None):
    """
    Detect facial landmarks in a portrait image.
    
    Args:
        image_path: Path to image file (RGB or BGR)
        downscale: int, reduce resolution for faster detection (1=native, 2=1/2, etc)
        target_size: Deprecated, kept for compatibility
    
    Returns:
        landmarks: np.array of shape (476, 2), pixel coordinates in original image space
                  [468 face mesh landmarks + 8 boundary anchor points]
        image: Original image (uint8, BGR)
    
    Raises:
        ValueError: If face not detected
        FileNotFoundError: If image_path doesn't exist
    """
    # Load image - np.fromfile handles non-ASCII paths on Windows
    raw = np.fromfile(str(image_path), dtype=np.uint8)
    if raw.size == 0:
        raise FileNotFoundError(f"Image not found: {image_path}")
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Could not decode image: {image_path}")
    
    h_orig, w_orig = image.shape[:2]
    
    # Optionally downscale for faster processing, then detect at reduced resolution
    if downscale > 1:
        image_downscaled = cv2.resize(image, (w_orig // downscale, h_orig // downscale))
        scale_x = w_orig / (w_orig // downscale)
        scale_y = h_orig / (h_orig // downscale)
    else:
        image_downscaled = image
        scale_x = 1.0
        scale_y = 1.0
    
    # Convert BGR to RGB for MediaPipe
    image_rgb = cv2.cvtColor(image_downscaled, cv2.COLOR_BGR2RGB)

    # Use FaceMesh for static image landmark extraction (468 points).
    with mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=False,
        min_detection_confidence=0.5,
    ) as face_mesh:
        result = face_mesh.process(image_rgb)

    if not result.multi_face_landmarks:
        raise ValueError(f"No face detected in {image_path}")

    # FaceMesh returns 468 normalized landmarks.
    face_landmarks = result.multi_face_landmarks[0].landmark
    landmarks_normalized = np.array(
        [[lm.x, lm.y] for lm in face_landmarks],
        dtype=np.float32
    )
    
    # Convert to pixel coordinates and scale back to original resolution
    landmarks = landmarks_normalized.copy()
    h_detect, w_detect = image_downscaled.shape[:2]
    landmarks[:, 0] *= w_detect
    landmarks[:, 1] *= h_detect
    landmarks[:, 0] *= scale_x
    landmarks[:, 1] *= scale_y
    
    # Clip to image bounds
    landmarks[:, 0] = np.clip(landmarks[:, 0], 0, w_orig - 1)
    landmarks[:, 1] = np.clip(landmarks[:, 1], 0, h_orig - 1)
    
    # Add 8 boundary anchor points to prevent edge distortion
    # (4 corners + 4 midpoints of edges)
    boundary_points = np.array([
        [0, 0],                          # top-left corner
        [w_orig - 1, 0],                 # top-right corner
        [w_orig - 1, h_orig - 1],        # bottom-right corner
        [0, h_orig - 1],                 # bottom-left corner
        [w_orig / 2, 0],                 # top edge midpoint
        [w_orig - 1, h_orig / 2],        # right edge midpoint
        [w_orig / 2, h_orig - 1],        # bottom edge midpoint
        [0, h_orig / 2],                 # left edge midpoint
    ], dtype=np.float32)
    
    landmarks = np.vstack([landmarks, boundary_points])
    
    return landmarks, image


def detect_landmarks_batch(photo_dir, downscale=1, target_size=None):
    """
    Detect landmarks for all images in a directory.
    
    Args:
        photo_dir: Path to folder containing portrait images
        downscale: int, factor to reduce resolution for faster detection (1=native, 2=1/2, etc)
        target_size: Deprecated, kept for compatibility
    
    Returns:
        landmarks_dict: {filename: np.array of landmarks}
        images_dict: {filename: image array at original resolution}
        filenames_ordered: List of filenames in order processed
    """
    from pathlib import Path
    
    photo_dir = Path(photo_dir)
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp'}
    
    landmarks_dict = {}
    images_dict = {}
    filenames_ordered = []
    
    # Collect image files sorted alphabetically
    image_files = sorted([
        f for f in photo_dir.iterdir()
        if f.suffix.lower() in image_extensions
    ])
    
    if not image_files:
        raise ValueError(f"No images found in {photo_dir}")
    
    for image_path in image_files:
        print(f"Detecting landmarks: {image_path.name}...", end=" ", flush=True)
        try:
            landmarks, image = detect_landmarks(image_path, downscale=downscale)
            landmarks_dict[image_path.name] = landmarks
            images_dict[image_path.name] = image
            filenames_ordered.append(image_path.name)
            print("✓")
        except ValueError as e:
            print(f"✗ {e}")
        except Exception as e:
            print(f"✗ Error: {e}")
    
    if not landmarks_dict:
        raise ValueError("Failed to detect landmarks in any images")
    
    return landmarks_dict, images_dict, filenames_ordered


def validate_landmarks_quality(image, landmarks):
    """
    Validate landmark quality for a single image.
    Returns a quality score (0.0-1.0; higher = better).
    
    Checks:
    - Face bounding box coverage (should be >20% of image)
    - Landmark spread (convex hull area >15% of image)
    - Symmetry (L/R eyes within tolerance)
    """
    h, w = image.shape[:2]
    image_area = h * w
    
    # Get face bounding rect from landmarks
    lm = landmarks[:468]  # Exclude boundary points
    bbox_x_min, bbox_y_min = lm.min(axis=0)
    bbox_x_max, bbox_y_max = lm.max(axis=0)
    bbox_area = (bbox_x_max - bbox_x_min) * (bbox_y_max - bbox_y_min)
    
    coverage = bbox_area / image_area if image_area > 0 else 0.0
    coverage_score = min(1.0, coverage / 0.3)  # Optimal ~30% coverage
    
    # Check for obvious failures (face too small or too large)
    if coverage < 0.05:
        return 0.1  # Face too small
    if coverage > 0.95:
        return 0.2  # Face fills entire image (unrealistic)
    
    # Symmetry check: compare L/R eye positions (landmarks 33 and 263)
    try:
        left_eye = landmarks[33]
        right_eye = landmarks[263]
        y_diff = abs(left_eye[1] - right_eye[1])
        eye_distance = np.linalg.norm(left_eye - right_eye)
        y_tolerance = eye_distance * 0.15
        symmetry_ok = y_diff < y_tolerance
        symmetry_score = 0.9 if symmetry_ok else 0.5
    except:
        symmetry_score = 0.5
    
    # Overall score
    quality = 0.5 * coverage_score + 0.5 * symmetry_score
    return quality


def load_images_batch(photo_dir):
    """
    Load images without detecting landmarks (use cached landmarks).
    
    Args:
        photo_dir: Path to folder
    
    Returns:
        images_dict: {filename: image}
        filenames_ordered: List of filenames
    """
    photo_dir = Path(photo_dir)
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp'}
    
    images_dict = {}
    filenames_ordered = []
    
    image_files = sorted([
        f for f in photo_dir.iterdir()
        if f.suffix.lower() in image_extensions
    ])
    
    if not image_files:
        raise ValueError(f"No images found in {photo_dir}")
    
    for image_path in image_files:
        try:
            raw = np.fromfile(str(image_path), dtype=np.uint8)
            if raw.size == 0:
                continue
            image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if image is not None:
                images_dict[image_path.name] = image
                filenames_ordered.append(image_path.name)
        except Exception as e:
            print(f"  Warning: skipped {image_path.name} ({e})")
    
    if not images_dict:
        raise ValueError("Failed to load any images")
    
    return images_dict, filenames_ordered
