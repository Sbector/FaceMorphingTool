#!/usr/bin/env python3
"""
Pipeline orchestrator for complete face morphing workflow.
Manages landmark editing, timing configuration, and video rendering.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from itertools import combinations
import os


def get_python_executable():
    """Get the Python executable path from venv, fallback to sys.executable."""
    venv_python = Path(".venv/Scripts/python.exe")
    if venv_python.exists():
        return str(venv_python.absolute())
    return sys.executable


def get_images_from_dir(photos_dir):
    """Load all images from photos directory."""
    photos_dir = Path(photos_dir)
    if not photos_dir.exists():
        print(f"[ERROR] Photos directory not found: {photos_dir}")
        sys.exit(1)
    
    images = sorted([
        f for f in photos_dir.glob("*.jpg") if f.is_file()
    ] + [
        f for f in photos_dir.glob("*.png") if f.is_file()
    ])
    
    if not images:
        print(f"[ERROR] No images found in {photos_dir}")
        sys.exit(1)
    
    return [img.name for img in images]


def compute_sequential_pairs(image_names):
    """Return list of (a, b) pairs for sequential mode: A->B->C->...->A."""
    n = len(image_names)
    pairs = []
    for i in range(n):
        a = image_names[i]
        b = image_names[(i + 1) % n]
        pairs.append((a, b))
    return pairs


def compute_all_pairs(image_names):
    """Return list of (a, b) pairs for all-pairs mode (Eulerian circuit)."""
    pairs = []
    for a, b in combinations(image_names, 2):
        pairs.append((a, b))
        pairs.append((b, a))
    return pairs


def generate_inverse_json(src_path, dst_path):
    """Generate inverted landmark JSON from existing file.
    
    Args:
        src_path: Path to existing A_B.json
        dst_path: Path where B_A.json should be written (must not exist)
    
    Returns:
        True if generated, False if dst_path already exists
    """
    if dst_path.exists():
        return False
    
    try:
        with open(src_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to read {src_path}: {e}")
        return False
    
    # Create inverted data
    inv_data = dict(data)
    
    # Swap images
    if 'image_a' in data and 'image_b' in data:
        inv_data['image_a'] = data['image_b']
        inv_data['image_b'] = data['image_a']
    
    # Swap image sizes
    if 'image_a_size' in data and 'image_b_size' in data:
        inv_data['image_a_size'] = data['image_b_size']
        inv_data['image_b_size'] = data['image_a_size']
    
    # Invert all pairs
    inv_pairs = []
    for i, pair in enumerate(data.get('pairs', [])):
        inv_pair = {
            'id': i,
            'a': pair['b'],
            'b': pair['a']
        }
        inv_pairs.append(inv_pair)
    
    inv_data['pairs'] = inv_pairs
    
    # Write inverted JSON
    try:
        with open(dst_path, 'w', encoding='utf-8') as f:
            json.dump(inv_data, f, ensure_ascii=False, indent=2)
        print(f"[AUTO] Inverted {src_path.name} → {dst_path.name}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to write {dst_path}: {e}")
        return False


def check_missing_landmarks(pairs, landmarks_dir):
    """Check which landmark JSON files are missing.
    
    Returns:
        auto_invertible: list of (a, b, json_path, json_path_inv) where b_a.json exists
        truly_missing: list of (a, b, json_path) where neither a_b nor b_a exists
    """
    landmarks_dir = Path(landmarks_dir)
    auto_invertible = []
    truly_missing = []
    
    for a, b in pairs:
        stem_a = Path(a).stem
        stem_b = Path(b).stem
        json_name = f"{stem_a}_{stem_b}.json"
        json_path = landmarks_dir / json_name
        json_path_inv = landmarks_dir / f"{stem_b}_{stem_a}.json"
        
        if not json_path.exists():
            if json_path_inv.exists():
                # Inverse exists, can auto-generate
                auto_invertible.append((a, b, json_path, json_path_inv))
            else:
                # Neither exists, need manual editing
                truly_missing.append((a, b, json_path))
    
    return auto_invertible, truly_missing


def create_session_json(missing_pairs, photos_dir, landmarks_dir, session_path):
    """Create temporary session.json with list of pairs to edit."""
    session_data = {
        "pairs": []
    }
    photos_root = Path(photos_dir).resolve()
    
    for a, b, json_path in missing_pairs:
        session_data["pairs"].append({
            "image_a": str((photos_root / a).resolve()),
            "image_b": str((photos_root / b).resolve()),
            "output": str(Path(json_path).resolve())
        })
    
    with open(session_path, "w") as f:
        json.dump(session_data, f, indent=2)
    
    print(f"[OK] Created session.json with {len(session_data['pairs'])} pairs to edit")
    return session_path


def ask_yes_no(prompt):
    """Ask user a yes/no question."""
    while True:
        response = input(f"{prompt} (s/n): ").strip().lower()
        if response in ("s", "y", "si", "yes"):
            return True
        elif response in ("n", "no"):
            return False
        else:
            print("  Please enter 's' or 'n'")


def ask_mode():
    """Ask user to choose morphing mode."""
    print("\n" + "="*60)
    print("Morphing Mode")
    print("="*60)
    print("  [1] Sequential (image1 -> image2 -> ... -> image1)")
    print("  [2] All-pairs with Eulerian circuit (visit all pairs once)")
    
    while True:
        choice = input("\nSelect mode [1-2]: ").strip()
        if choice in ("1", "2"):
            return "sequential" if choice == "1" else "all-pairs"
        print("  Invalid choice. Please enter 1 or 2")


def main():
    parser = argparse.ArgumentParser(
        description="Complete face morphing pipeline"
    )
    parser.add_argument("--photos", default="photos", help="Photos directory")
    parser.add_argument("--landmarks-dir", default="landmarks", help="Landmarks directory")
    parser.add_argument("--output", default="output/morph.mp4", help="Output video path")
    parser.add_argument("--profile", default="preview", choices=["preview", "final"])
    parser.add_argument("--mode", choices=["sequential", "all-pairs"], help="Override mode selection")
    parser.add_argument("--skip-editor", action="store_true", help="Skip landmark editing")
    parser.add_argument("--skip-timing", action="store_true", help="Skip timing editor")
    parser.add_argument("--use-cache", action="store_true", help="Use cached landmarks in morph.py")
    
    args = parser.parse_args()
    
    # Create directories if needed
    Path(args.landmarks_dir).mkdir(exist_ok=True)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*60)
    print("FACE MORPHER - COMPLETE PIPELINE")
    print("="*60)
    
    # Step 1: Get images
    print(f"\n[STEP 1] Scanning photos directory: {args.photos}")
    image_names = get_images_from_dir(args.photos)
    print(f"[OK] Found {len(image_names)} images: {', '.join([Path(n).stem for n in image_names])}")
    
    # Step 2: Choose mode
    print(f"\n[STEP 2] Select morphing mode")
    mode = args.mode or ask_mode()
    print(f"[OK] Mode: {mode}")
    
    if mode == "sequential":
        pairs = compute_sequential_pairs(image_names)
    else:  # all-pairs
        pairs = compute_all_pairs(image_names)
    
    print(f"[INFO] Will create transitions: {len(pairs)} pairs")
    
    # Step 3: Check for missing landmarks
    print(f"\n[STEP 3] Checking landmark files in {args.landmarks_dir}")
    auto_invertible, truly_missing = check_missing_landmarks(pairs, args.landmarks_dir)
    
    # Step 3.5: Auto-generate inverted JSONs
    if auto_invertible:
        print(f"\n[STEP 3.5] Auto-generating {len(auto_invertible)} inverted landmark files...")
        generated = 0
        for a, b, dst_path, src_path in auto_invertible:
            if generate_inverse_json(src_path, dst_path):
                generated += 1
        print(f"[OK] Generated {generated} inverted files")
    
    if not auto_invertible and not truly_missing:
        print(f"[OK] All {len(pairs)} landmark files exist")
    elif truly_missing:
        print(f"[WARNING] {len(truly_missing)} landmark files still missing (no inverse found):")
        for a, b, json_path in truly_missing[:3]:
            print(f"  - {json_path.name}")
        if len(truly_missing) > 3:
            print(f"  ... and {len(truly_missing)-3} more")
    else:
        print(f"[OK] All remaining landmark files auto-generated")
    
    # Step 4: Edit landmarks if needed
    if truly_missing and not args.skip_editor:
        print(f"\n[STEP 4] Opening landmark editor for {len(truly_missing)} pairs")
        
        session_path = Path("session.json")
        create_session_json(truly_missing, args.photos, args.landmarks_dir, session_path)
        
        print("[INFO] Launching landmark_editor.py in session mode...")
        print("[INFO] Tips: Press 'A' for auto-seed, 'N' to go to next pair, 'S' to save")
        
        result = subprocess.call([
            get_python_executable(),
            "landmark_editor.py",
            "--session", str(session_path)
        ])
        
        if result != 0:
            print("[ERROR] Landmark editor exited with error")
            sys.exit(1)
        
        # Clean up session file
        session_path.unlink(missing_ok=True)
        print("[OK] Landmark editing complete")
    elif args.skip_editor and (truly_missing or auto_invertible):
        print(f"\n[STEP 4] Skipped landmark editing (--skip-editor)")
    else:
        print(f"\n[STEP 4] No landmark editing needed")
    
    # Step 5: Timing editor
    if not args.skip_timing and ask_yes_no("\n[STEP 5] Configure timing?"):
        print("[INFO] Launching timing_editor.py...")
        result = subprocess.call([
            get_python_executable(),
            "timing_editor.py",
            "--load"
        ])
        if result != 0:
            print("[ERROR] Timing editor exited with error")
            sys.exit(1)
        print("[OK] Timing configuration complete")
    else:
        print(f"\n[STEP 5] Skipped timing editor")
    
    # Step 6: Render video
    print(f"\n[STEP 6] Rendering video with morph.py")
    
    # Prepare morph.py arguments
    morph_args = [
        get_python_executable(),
        "morph.py",
        "--photos", args.photos,
        "--points-dir", args.landmarks_dir,
        "--profile", args.profile,
        "--mode", mode,
        "--output", args.output
    ]
    
    if args.use_cache:
        morph_args.append("--use-cache")
    
    print(f"[INFO] Rendering: {' '.join(morph_args[2:])}")
    result = subprocess.call(morph_args)
    
    if result != 0:
        print("[ERROR] morph.py failed")
        sys.exit(1)
    
    # Success
    print("\n" + "="*60)
    print("[OK] PIPELINE COMPLETE")
    print("="*60)
    print(f"Video saved: {args.output}")
    print(f"Mode: {mode}")
    print(f"Pairs: {len(pairs)}")
    print()


if __name__ == "__main__":
    main()
