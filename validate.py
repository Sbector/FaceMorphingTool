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
