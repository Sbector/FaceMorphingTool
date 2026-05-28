#!/usr/bin/env python3
"""
review.py - Batch review and edit existing landmark pairs in session mode.

This tool scans a landmarks directory and opens all existing landmark JSONs
in the landmark_editor in session mode, allowing fine-tuning of all pairs.

Usage:
    python review.py --photos photos --landmarks-dir landmarks
    python review.py --photos photos --landmarks-dir landmarks --filter "1_*"
    python review.py --photos photos --landmarks-dir landmarks --display-width 400
"""

import json
import sys
import subprocess
import argparse
from pathlib import Path
from fnmatch import filter as fnmatch_filter


def main():
    parser = argparse.ArgumentParser(
        description="Review and edit all landmark pairs in batch session mode"
    )
    parser.add_argument(
        "--photos",
        default="photos",
        help="Directory containing source images (default: photos)"
    )
    parser.add_argument(
        "--landmarks-dir",
        default="landmarks",
        help="Directory containing landmark JSON files (default: landmarks)"
    )
    parser.add_argument(
        "--display-width",
        type=int,
        help="Display width per panel in pixels (optional)"
    )
    parser.add_argument(
        "--filter",
        default="*.json",
        help="Filter landmark files by glob pattern (default: *.json)"
    )

    args = parser.parse_args()

    photos_dir = Path(args.photos)
    landmarks_dir = Path(args.landmarks_dir)
    display_width = args.display_width
    filter_pattern = args.filter if "*" in args.filter else f"*{args.filter}*"

    # Validate directories exist
    if not photos_dir.exists():
        print(f"[ERROR] Photos directory not found: {photos_dir}")
        return 1

    if not landmarks_dir.exists():
        print(f"[ERROR] Landmarks directory not found: {landmarks_dir}")
        return 1

    # Scan landmark JSONs and filter
    all_jsons = sorted(landmarks_dir.glob("*.json"))
    filtered_jsons = [f for f in all_jsons if any(fnmatch_filter([f.name], filter_pattern))]

    if not filtered_jsons:
        print(f"[ERROR] No landmark files matching '{filter_pattern}' in {landmarks_dir}")
        return 1

    print(f"[INFO] Found {len(filtered_jsons)} landmark file(s) to review")
    print()

    # Build session data
    session_pairs = []

    for json_path in filtered_jsons:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                landmark_data = json.load(f)

            # Extract image filenames from JSON
            image_a = landmark_data.get('image_a')
            image_b = landmark_data.get('image_b')

            if not image_a or not image_b:
                print(f"[SKIP] {json_path.name}: missing image_a or image_b in JSON")
                continue

            # Resolve image paths
            image_a_path = photos_dir / Path(image_a).name
            image_b_path = photos_dir / Path(image_b).name

            # Verify images exist
            if not image_a_path.exists():
                print(f"[SKIP] {json_path.name}: image not found: {image_a_path}")
                continue

            if not image_b_path.exists():
                print(f"[SKIP] {json_path.name}: image not found: {image_b_path}")
                continue

            # Add to session
            session_pairs.append({
                "image_a": str(image_a_path.resolve()),
                "image_b": str(image_b_path.resolve()),
                "landmarks": str(json_path.resolve())
            })

            print(f"[OK] {json_path.name}")

        except Exception as e:
            print(f"[ERROR] {json_path.name}: {e}")
            continue

    if not session_pairs:
        print("\n[ERROR] No valid pairs to review")
        return 1

    print(f"\n[INFO] Prepared {len(session_pairs)} pair(s) for review")

    # Write temporary session file
    session_file = Path("_review_session.json")
    session_data = {"pairs": session_pairs}

    try:
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2)
        print(f"[OK] Created temporary session file: {session_file}")
    except Exception as e:
        print(f"[ERROR] Failed to write session file: {e}")
        return 1

    # Build landmark_editor command
    editor_cmd = ["python", "landmark_editor.py", "--session", str(session_file)]

    if display_width:
        editor_cmd.extend(["--display-width", str(display_width)])

    # Launch editor
    print(f"\n[INFO] Launching landmark editor in session mode...")
    print(f"[INFO] Keyboard shortcuts: N=next pair, P=prev pair, S=save, Q=quit")
    print("-" * 60)

    try:
        result = subprocess.call(editor_cmd)
    except Exception as e:
        print(f"[ERROR] Failed to launch editor: {e}")
        if session_file.exists():
            session_file.unlink()
        return 1

    # Cleanup temporary session file
    if session_file.exists():
        try:
            session_file.unlink()
            print(f"[OK] Cleaned up temporary session file")
        except Exception as e:
            print(f"[WARN] Failed to cleanup {session_file}: {e}")

    print(f"\n[OK] Review completed")
    return result


if __name__ == "__main__":
    sys.exit(main())
