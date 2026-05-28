"""
Timing configuration editor for face morphing.
Creates a GUI with trackbars to adjust Duration, Hold, and FPS.
Saves config to morph_config.json.

Usage:
  python timing_editor.py [--load]
  
Keys:
  s = Save config
  q = Quit
"""

import argparse
import json
import sys
from pathlib import Path
import cv2
import numpy as np


class TimingEditor:
    def __init__(self, load_existing=False):
        """
        Initialize timing editor.
        
        Args:
            load_existing: bool, load existing morph_config.json if it exists
        """
        self.config_path = Path('morph_config.json')
        
        # Default values
        self.duration = 2.0  # seconds
        self.hold = 0.8      # seconds
        self.fps = 30        # frames per second
        
        # Load existing config if requested and available
        if load_existing and self.config_path.exists():
            self.load_config()
        
        # Convert to trackbar ranges (x0.1 for duration/hold, direct for fps)
        self.trackbar_duration = int(self.duration * 10)  # 1-100 = 0.1-10.0s
        self.trackbar_hold = int(self.hold * 10)          # 0-50 = 0.0-5.0s
        self.trackbar_fps = self.fps                       # 12-60 fps
    
    def load_config(self):
        """Load config from morph_config.json."""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            self.duration = data.get('duration', 2.0)
            self.hold = data.get('hold', 0.8)
            self.fps = data.get('fps', 30)
            print(f"✓ Loaded config: duration={self.duration}s, hold={self.hold}s, fps={self.fps}")
        except Exception as e:
            print(f"✗ Failed to load config: {e}")
    
    def save_config(self):
        """Save config to morph_config.json."""
        # Convert trackbar values back to real values
        duration = self.trackbar_duration / 10.0
        hold = self.trackbar_hold / 10.0
        fps = self.trackbar_fps
        
        data = {
            'duration': round(duration, 1),
            'hold': round(hold, 2),
            'fps': fps,
        }
        
        try:
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"✓ Saved config: duration={data['duration']}s, hold={data['hold']}s, fps={data['fps']}")
            return True
        except Exception as e:
            print(f"✗ Failed to save config: {e}")
            return False
    
    def create_canvas(self):
        """Create status canvas with text display."""
        canvas = np.ones((180, 600, 3), dtype=np.uint8) * 240
        
        # Calculate current values from trackbars
        duration = self.trackbar_duration / 10.0
        hold = self.trackbar_hold / 10.0
        fps = self.trackbar_fps
        
        # Draw titles and values
        cv2.putText(canvas, "Timing Configuration", (20, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        
        y_offset = 55
        line_height = 30
        
        # Duration
        cv2.putText(canvas, f"Duration: {duration:.1f}s", (30, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (50, 50, 200), 1)
        
        # Hold
        cv2.putText(canvas, f"Hold: {hold:.2f}s", (30, y_offset + line_height),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (50, 50, 200), 1)
        
        # FPS
        cv2.putText(canvas, f"FPS: {fps}", (30, y_offset + 2*line_height),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (50, 50, 200), 1)
        
        # Instructions
        cv2.putText(canvas, "Press 's' to Save  |  'q' to Quit", (30, y_offset + 3*line_height + 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
        
        return canvas
    
    def run(self):
        """Main event loop."""
        window_name = "Timing Editor"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 600, 300)
        
        print(f"\n{'='*60}")
        print("Timing Editor")
        print(f"{'='*60}")
        print("Adjust the trackbars below to configure morphing timing")
        print("  Duration: transition time (0.1 - 10.0 seconds)")
        print("  Hold:     static image time (0.0 - 5.0 seconds)")
        print("  FPS:      frames per second (12 - 60 fps)")
        print(f"\nPress 's' to Save  |  'q' to Quit")
        print(f"{'='*60}\n")
        
        # Create trackbars
        def update_duration(val):
            self.trackbar_duration = val
        
        def update_hold(val):
            self.trackbar_hold = val
        
        def update_fps(val):
            self.trackbar_fps = val
        
        cv2.createTrackbar('Duration (x0.1s)', window_name, self.trackbar_duration, 100, update_duration)
        cv2.createTrackbar('Hold (x0.1s)', window_name, self.trackbar_hold, 50, update_hold)
        cv2.createTrackbar('FPS', window_name, self.trackbar_fps, 60, update_fps)
        
        # Main loop
        while True:
            canvas = self.create_canvas()
            cv2.imshow(window_name, canvas)
            
            key = cv2.waitKey(100) & 0xFF
            if key == ord('s'):
                if self.save_config():
                    print("Configuration saved successfully!")
            elif key == ord('q'):
                break
        
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description='Configure morphing timing parameters')
    parser.add_argument('--load', action='store_true', help='Load existing config on startup')
    
    args = parser.parse_args()
    
    try:
        editor = TimingEditor(load_existing=args.load)
        editor.run()
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
