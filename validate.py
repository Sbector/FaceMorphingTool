#!/usr/bin/env python3
import json
import os
from pathlib import Path

# Dynamically scan landmarks directory
landmarks_dir = Path("landmarks")
files = sorted([str(f) for f in landmarks_dir.glob("*.json")])

if not files:
    print("[ERROR] No landmark JSON files found in landmarks/")
    exit(1)

#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import cv2


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate landmark JSON files against the current photo set"
    )
    parser.add_argument(
        "--photos",
        default="photos",
        help="Directory containing source images (default: photos)",
    )
    parser.add_argument(
        "--landmarks-dir",
        default="landmarks",
        help="Directory containing landmark JSON files (default: landmarks)",
    )
    return parser.parse_args()


def load_json(json_path):
    with open(json_path, encoding="utf-8-sig") as file_handle:
        return json.load(file_handle)


def read_image_size(image_path):
    image = cv2.imread(str(image_path))
    if image is None:
        return None
    height, width = image.shape[:2]
    return [width, height]


def validate_point(point, bounds):
    if not isinstance(point, list) or len(point) != 2:
        return False
    if not all(isinstance(value, (int, float)) for value in point):
        return False

    max_width, max_height = bounds
    x_coord, y_coord = point
    return 0 <= x_coord <= max_width and 0 <= y_coord <= max_height


def validate_file(json_path, photos_dir):
    issues = []

    try:
        data = load_json(json_path)
    except Exception as exc:
        return None, [f"invalid json: {exc}"]

    image_a_name = data.get("image_a")
    image_b_name = data.get("image_b")
    if not image_a_name or not image_b_name:
        return data, ["missing image_a or image_b"]

    image_a_path = photos_dir / Path(image_a_name).name
    image_b_path = photos_dir / Path(image_b_name).name

    actual_size_a = read_image_size(image_a_path)
    actual_size_b = read_image_size(image_b_path)
    if actual_size_a is None:
        issues.append(f"missing image: {image_a_path}")
    if actual_size_b is None:
        issues.append(f"missing image: {image_b_path}")
    if issues:
        return data, issues

    declared_size_a = data.get("image_a_size")
    declared_size_b = data.get("image_b_size")
    if declared_size_a != actual_size_a:
        issues.append(
            f"image_a_size mismatch: json={declared_size_a} actual={actual_size_a}"
        )
    if declared_size_b != actual_size_b:
        issues.append(
            f"image_b_size mismatch: json={declared_size_b} actual={actual_size_b}"
        )

    pairs = data.get("pairs")
    if not isinstance(pairs, list):
        issues.append("pairs is not a list")
        return data, issues

    bad_points = 0
    malformed_pairs = 0
    bounds_a = (actual_size_a[0], actual_size_a[1])
    bounds_b = (actual_size_b[0], actual_size_b[1])
    for pair in pairs:
        if not isinstance(pair, dict):
            malformed_pairs += 1
            continue

        point_a = pair.get("a")
        point_b = pair.get("b")
        if not validate_point(point_a, bounds_a) or not validate_point(point_b, bounds_b):
            bad_points += 1

    if malformed_pairs:
        issues.append(f"malformed pair entries: {malformed_pairs}")
    if bad_points:
        issues.append(f"pairs out of bounds or malformed coordinates: {bad_points}")

    return data, issues


def compare_inverse_pairs(file_results):
    warnings = []
    seen = set()

    for json_path, data in file_results.items():
        stem_parts = json_path.stem.split("_", 1)
        if len(stem_parts) != 2:
            continue

        source_name, target_name = stem_parts
        inverse_name = f"{target_name}_{source_name}.json"
        inverse_path = json_path.with_name(inverse_name)
        pair_key = tuple(sorted((json_path.name, inverse_name)))
        if pair_key in seen or inverse_path not in file_results:
            continue

        seen.add(pair_key)
        inverse_data = file_results[inverse_path]
        pair_count = len(data.get("pairs", []))
        inverse_pair_count = len(inverse_data.get("pairs", []))
        if pair_count != inverse_pair_count:
            warnings.append(
                f"inverse mismatch: {json_path.name} has {pair_count} pairs, "
                f"{inverse_path.name} has {inverse_pair_count}"
            )

    return warnings


def main():
    args = parse_args()
    photos_dir = Path(args.photos)
    landmarks_dir = Path(args.landmarks_dir)

    if not photos_dir.exists():
        print(f"[ERROR] Photos directory not found: {photos_dir}")
        return 1
    if not landmarks_dir.exists():
        print(f"[ERROR] Landmarks directory not found: {landmarks_dir}")
        return 1

    files = sorted(landmarks_dir.glob("*.json"))
    if not files:
        print(f"[ERROR] No landmark JSON files found in {landmarks_dir}")
        return 1

    print("\n=== LANDMARK FILES VALIDATION ===\n")
    total_pairs = 0
    ok_files = 0
    warn_files = 0
    valid_data = {}

    for json_path in files:
        data, issues = validate_file(json_path, photos_dir)
        pair_count = len(data.get("pairs", [])) if isinstance(data, dict) else 0
        total_pairs += pair_count

        if issues:
            warn_files += 1
            print(f"[WARN] {json_path}: {pair_count} pairs")
            for issue in issues:
                print(f"       - {issue}")
        else:
            ok_files += 1
            valid_data[json_path] = data
            print(f"[OK]   {json_path}: {pair_count} pairs")

    inverse_warnings = compare_inverse_pairs(valid_data)
    if inverse_warnings:
        print("\n=== INVERSE PAIR CHECKS ===\n")
        for warning in inverse_warnings:
            print(f"[WARN] {warning}")

    total_warnings = warn_files + len(inverse_warnings)
    print(
        f"\n=== SUMMARY: {ok_files} ok, {total_warnings} warnings, {total_pairs} total pairs ===\n"
    )
    return 0 if total_warnings == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
print("\n=== LANDMARK FILES VALIDATION ===\n")
total_pairs = 0
for f in files:
    if os.path.exists(f):
        try:
            with open(f) as fp:
                data = json.load(fp)
                pairs = len(data.get('pairs', []))
                total_pairs += pairs
                print(f"✓ {f}: {pairs} pairs")
        except Exception as e:
            print(f"✗ {f}: ERROR - {e}")
    else:
        print(f"✗ {f}: MISSING")

print(f"\n=== TOTAL: {total_pairs} pairs across all files ===\n")
