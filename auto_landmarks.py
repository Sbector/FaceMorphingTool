#!/usr/bin/env python3
"""Auto-generate landmark JSONs for all pairs using MediaPipe."""

import json
import cv2
from pathlib import Path
from itertools import combinations
from detect import detect_landmarks

# Import KEY_LANDMARK_INDICES from landmark_editor if available, else use default 30
try:
    from landmark_editor import KEY_LANDMARK_INDICES
except ImportError:
    # Fallback: use first 30 points if import fails
    KEY_LANDMARK_INDICES = list(range(30))

def generate_pair_landmarks(img_a_path, img_b_path, output_json):
    """Generate landmarks for a pair using MediaPipe auto-detection."""
    
    # Detect landmarks
    result_a = detect_landmarks(str(img_a_path))
    result_b = detect_landmarks(str(img_b_path))
    
    if result_a is None or result_b is None:
        print(f"[SKIP] Could not detect landmarks for {img_a_path} or {img_b_path}")
        return False
    
    # Result is (landmarks, image) tuple
    if isinstance(result_a, tuple):
        lm_a, _ = result_a
    else:
        lm_a = result_a
    
    if isinstance(result_b, tuple):
        lm_b, _ = result_b
    else:
        lm_b = result_b
    
    # Convert to correspondence format (pick key points)
    pairs = []
    for i, idx in enumerate(KEY_LANDMARK_INDICES):
        if idx < len(lm_a) and idx < len(lm_b):
            pairs.append({
                "id": i,
                "a": [float(lm_a[idx][0]), float(lm_a[idx][1])],
                "b": [float(lm_b[idx][0]), float(lm_b[idx][1])]
            })
    
    # Get image info
    img_a = cv2.imread(str(img_a_path))
    img_b = cv2.imread(str(img_b_path))
    h_a, w_a = img_a.shape[:2] if img_a is not None else (1920, 1080)
    h_b, w_b = img_b.shape[:2] if img_b is not None else (1920, 1080)
    
    data = {
        "image_a": Path(img_a_path).name,
        "image_b": Path(img_b_path).name,
        "image_a_size": [w_a, h_a],
        "image_b_size": [w_b, h_b],
        "pairs": pairs
    }
    
    # Write JSON
    output_json.parent.mkdir(exist_ok=True)
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] Generated {output_json.name} with {len(pairs)} points")
    return True

def main():
    photos_dir = Path("photos")
    landmarks_dir = Path("landmarks")
    
    images = sorted([
        f for f in photos_dir.glob("*.png") if f.is_file()
    ] + [
        f for f in photos_dir.glob("*.jpg") if f.is_file()
    ])
    
    if not images:
        print("[ERROR] No images found in photos")
        return
    
    print(f"[INFO] Found {len(images)} images")
    print(f"[INFO] Using {len(KEY_LANDMARK_INDICES)} key points per pair")
    
    # Generate one-direction pairs (only A->B, not B->A)
    count = 0
    for i, img_a in enumerate(images):
        for img_b in images[i+1:]:
            a_stem = img_a.stem
            b_stem = img_b.stem
            output_json = landmarks_dir / f"{a_stem}_{b_stem}.json"
            
            if output_json.exists():
                print(f"[SKIP] {output_json.name} already exists")
            else:
                if generate_pair_landmarks(img_a, img_b, output_json):
                    count += 1
    
    print(f"\n[OK] Generated {count} new landmark pairs (A->B only)")
    print(f"[INFO] Run pipeline with --mode all-pairs to auto-generate inverses (B->A)")

if __name__ == "__main__":
    main()
