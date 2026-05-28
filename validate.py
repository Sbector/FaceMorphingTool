#!/usr/bin/env python3
import json
import os

files = [
    'landmarks/Yo_Hermana.json',
    'landmarks/Hermana_Hermano.json',
    'landmarks/Hermano_Mamá.json',
    'landmarks/Mamá_Papá.json',
    'landmarks/Papá_Yo.json'
]

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
