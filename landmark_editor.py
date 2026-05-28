"""
Interactive OpenCV UI for creating face correspondence points.
Place ~30 pairs of points between two face images to guide TPS morphing.

Usage:
  python landmark_editor.py --image-a photos/Hermana.jpg --image-b photos/Hermano.jpg
  python landmark_editor.py --image-a photos/Hermana.jpg --image-b photos/Hermano.jpg --output landmarks/custom.json
  python landmark_editor.py --session morph_config.json

Keybinds:
  Left-click (left image)  → Start placing point in A
  Left-click (right image) → Complete pair in B
  Right-click              → Select closest point (radius 15px)
  Drag (when selected)     → Move selected point
  Delete/Backspace         → Delete selected pair
  
  s                        → Save JSON
  u                        → Undo last pair
  a                        → Auto-seed 30 semantic points from MediaPipe
  r                        → Reset (confirm clear all)
  l                        → Load existing JSON if available
  n                        → Next session pair
  p                        → Previous session pair
  q                        → Quit (confirm if unsaved)
"""

import argparse
import json
import sys
from pathlib import Path
import cv2
import numpy as np

from detect import detect_landmarks


# MediaPipe landmark indices for semantic key features
KEY_LANDMARK_INDICES = [
    1,    # nariz: tip
    168,  # nariz: puente
    6,    # nariz: dorso
    197,  # nariz: raíz
    33,   # ojo izq: canto interno
    133,  # ojo izq: canto externo
    159,  # ojo izq: párpado superior
    145,  # ojo izq: párpado inferior
    362,  # ojo der: canto interno
    263,  # ojo der: canto externo
    386,  # ojo der: párpado superior
    374,  # ojo der: párpado inferior
    70,   # ceja izq: medial
    107,  # ceja izq: lateral
    55,   # ceja izq: punta
    300,  # ceja der: medial
    336,  # ceja der: lateral
    285,  # ceja der: punta
    61,   # boca: comisura izq
    291,  # boca: comisura der
    13,   # boca: labio sup centro
    14,   # boca: labio inf centro
    17,   # barbilla
    152,  # mentón
    234,  # mejilla izq (lateral)
    454,  # mejilla der (lateral)
    10,   # frente: centro
    151,  # frente: abajo
    172,  # mandíbula izq
    397,  # mandíbula der
]


class LandmarkEditor:
    def __init__(self, image_a_path=None, image_b_path=None, display_width=None, output_json=None, session_json=None):
        """
        Initialize editor with two images or session mode.
        
        Args:
            image_a_path: str or None, path to first image
            image_b_path: str or None, path to second image
            display_width: int or None, width per panel in pixels (None = auto-fit to screen)
            output_json: str or None, output JSON path (default: landmarks/{stem_a}_{stem_b}.json)
            session_json: str or None, session JSON file with list of pairs to edit
        """
        self.display_width = display_width  # None = auto-compute in _update_display_sizes
        self.session_json_path = Path(session_json) if session_json else None
        self.session_pairs = []  # For session mode
        self.current_session_idx = 0  # Current pair in session mode
        self.session_mode = session_json is not None

        # Zoom / pan state (per panel, in original image coords)
        self.zoom_a = 1.0
        self.pan_ax = 0.0
        self.pan_ay = 0.0
        self.zoom_b = 1.0
        self.pan_bx = 0.0
        self.pan_by = 0.0

        # Middle-button drag for pan
        self.mid_drag_active = False
        self.mid_drag_start = (0, 0)
        self.mid_drag_panel = None
        self.mid_drag_pan_start = (0.0, 0.0, 0.0, 0.0)  # (pan_ax, pan_ay, pan_bx, pan_by)

        # Hover tracking for highlight ring
        self.hover_x = -1
        self.hover_y = -1

        # Navigation state
        self.nav_clicked = None  # Will be set to 'prev' or 'next' when nav bar clicked

        # Auto-seed confirmation flag
        self.auto_seed_pending = False

        if self.session_mode:
            self._load_session_pair()
        else:
            self._init_with_images(image_a_path, image_b_path, output_json)
    
    def _init_with_images(self, image_a_path, image_b_path, output_json):
        """Initialize with two image paths."""
        if not image_a_path or not image_b_path:
            raise ValueError("image_a_path and image_b_path are required in non-session mode")
        
        self.image_a_path = Path(image_a_path)
        self.image_b_path = Path(image_b_path)
        
        # Load images (handle UTF-8 paths properly on Windows)
        def load_image_robust(path):
            path_obj = Path(path)
            # Try direct path first (works on most systems)
            img = cv2.imread(str(path_obj))
            if img is None:
                # Fall back to imdecode for UTF-8 paths
                import numpy as np
                img = cv2.imdecode(np.fromfile(path_obj, dtype=np.uint8), cv2.IMREAD_COLOR)
            return img
        
        self.img_a_orig = load_image_robust(image_a_path)
        self.img_b_orig = load_image_robust(image_b_path)
        
        if self.img_a_orig is None or self.img_b_orig is None:
            raise RuntimeError(f"Failed to load images: {image_a_path}, {image_b_path}")
        
        # Output path
        if output_json:
            self.output_json = Path(output_json)
        else:
            stem_a = self.image_a_path.stem
            stem_b = self.image_b_path.stem
            self.output_json = Path('landmarks') / f"{stem_a}_{stem_b}.json"
        
        self.output_json.parent.mkdir(parents=True, exist_ok=True)
        
        # State
        self.pairs = []  # list of {'a': [x, y], 'b': [x, y]}
        self.pending_a = None
        self.selected_idx = None
        self.selected_side = None  # 'a' or 'b'
        self.drag_active = False  # Track if currently dragging a point
        self.dirty = False
        self.frame_count = 0  # for blinking
        
        # Try to load existing JSON
        if self.output_json.exists():
            self.load_json()
        
        # Update display sizes
        self._update_display_sizes()
    
    def _load_session_pair(self):
        """Load session mode and initialize with first pair."""
        try:
            with open(self.session_json_path, 'r') as f:
                session_data = json.load(f)
            
            # Extract pairs from session format
            self.session_pairs = session_data.get('pairs', [])
            if not self.session_pairs:
                raise ValueError("No pairs found in session JSON")
            
            self.current_session_idx = 0
            self._init_session_pair_at_index(0)
            
        except Exception as e:
            raise RuntimeError(f"Failed to load session JSON {self.session_json_path}: {e}")
    
    def _init_session_pair_at_index(self, idx):
        """Initialize editor for a specific pair in session mode."""
        if idx < 0 or idx >= len(self.session_pairs):
            raise ValueError(f"Invalid session pair index {idx}, available: {len(self.session_pairs)}")
        
        pair_data = self.session_pairs[idx]
        self.current_session_idx = idx
        
        # Load image paths from pair data
        image_a_path = pair_data.get('image_a')
        image_b_path = pair_data.get('image_b')
        landmarks_json = pair_data.get('landmarks') or pair_data.get('output')
        
        if not image_a_path or not image_b_path:
            raise ValueError(f"Session pair {idx} missing image paths")
        
        self.image_a_path = Path(image_a_path)
        self.image_b_path = Path(image_b_path)
        
        # Load images
        def load_image_robust(path):
            path_obj = Path(path)
            img = cv2.imread(str(path_obj))
            if img is None:
                import numpy as np
                img = cv2.imdecode(np.fromfile(path_obj, dtype=np.uint8), cv2.IMREAD_COLOR)
            return img
        
        self.img_a_orig = load_image_robust(image_a_path)
        self.img_b_orig = load_image_robust(image_b_path)
        
        if self.img_a_orig is None or self.img_b_orig is None:
            raise RuntimeError(f"Failed to load session images: {image_a_path}, {image_b_path}")
        
        # Output path from landmarks reference
        if landmarks_json:
            self.output_json = Path(landmarks_json)
        else:
            stem_a = self.image_a_path.stem
            stem_b = self.image_b_path.stem
            self.output_json = Path('landmarks') / f"{stem_a}_{stem_b}.json"
        
        self.output_json.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize state
        self.pairs = []
        self.pending_a = None
        self.selected_idx = None
        self.selected_side = None
        self.drag_active = False
        self.dirty = False
        self.frame_count = 0

        # Reset zoom/pan for new pair
        self.zoom_a = 1.0
        self.pan_ax = 0.0
        self.pan_ay = 0.0
        self.zoom_b = 1.0
        self.pan_bx = 0.0
        self.pan_by = 0.0
        
        # Load existing landmarks if available
        if self.output_json.exists():
            self.load_json()
        
        # Update display sizes
        self._update_display_sizes()

    @staticmethod
    def _get_screen_size():
        """Get screen dimensions (Windows). Fallback to 1920x1080 if unavailable."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            screen_w = user32.GetSystemMetrics(0)
            screen_h = user32.GetSystemMetrics(1)
            return screen_w, screen_h
        except:
            return 1920, 1080
    
    def _update_display_sizes(self):
        """Update display image sizes and scaling factors."""
        h_a, w_a = self.img_a_orig.shape[:2]
        h_b, w_b = self.img_b_orig.shape[:2]

        # Auto-compute display_width once (if not user-specified)
        if self.display_width is None:
            # Constrain by max panel height (based on screen size)
            screen_w, screen_h = self._get_screen_size()
            overhead = 40 + 35 + 25 + 60  # nav + help + status + taskbar
            max_panel_h = screen_h - overhead
            self.display_width = min(int(max_panel_h * w_a / h_a), (screen_w - 5) // 2)
            self.display_width = max(200, self.display_width)  # Minimum 200px

        # Scale factors at zoom=1.0
        self.scale_a = self.display_width / w_a
        self.scale_b = self.display_width / w_b

        # Fixed display height (base, zoom=1.0)
        new_h_a = int(h_a * self.scale_a)
        new_h_b = int(h_b * self.scale_b)
        self.img_a_disp = cv2.resize(self.img_a_orig, (self.display_width, new_h_a))
        self.img_b_disp = cv2.resize(self.img_b_orig, (self.display_width, new_h_b))

        # Pad both panels to same height for side-by-side display
        max_h = max(new_h_a, new_h_b)
        if new_h_a < max_h:
            pad = max_h - new_h_a
            self.img_a_disp = cv2.copyMakeBorder(self.img_a_disp, 0, pad, 0, 0, cv2.BORDER_CONSTANT, (48, 48, 48))
        if new_h_b < max_h:
            pad = max_h - new_h_b
            self.img_b_disp = cv2.copyMakeBorder(self.img_b_disp, 0, pad, 0, 0, cv2.BORDER_CONSTANT, (48, 48, 48))

        self.disp_h, _ = self.img_a_disp.shape[:2]

        # Separator (vertical divider between panels)
        self.separator = np.ones((self.disp_h, 5, 3), dtype=np.uint8) * 128
    
    def load_json(self):
        """Load correspondence points from existing JSON file."""
        try:
            with open(self.output_json, 'r') as f:
                data = json.load(f)
            self.pairs = data.get('pairs', [])
            print(f"Loaded {len(self.pairs)} pairs from {self.output_json}")
            self.dirty = False
        except Exception as e:
            print(f"Failed to load JSON: {e}")
    
    def save_json(self):
        """Save correspondence points to JSON file."""
        data = {
            'image_a': self.image_a_path.name,
            'image_b': self.image_b_path.name,
            'image_a_size': list(self.img_a_orig.shape[:2][::-1]),  # [w, h]
            'image_b_size': list(self.img_b_orig.shape[:2][::-1]),
            'pairs': self.pairs,
        }
        
        try:
            with open(self.output_json, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"[OK] Saved {len(self.pairs)} pairs to {self.output_json}")
            self.dirty = False
        except Exception as e:
            print(f"[ERROR] Failed to save: {e}")
    
    def point_in_image_a(self, x, y):
        """Check if point is in left (A) half of display (x in image-local coords)."""
        return x < self.display_width

    @property
    def nav_offset(self):
        """Y offset of image area due to nav bar (session mode only)."""
        return 40 if self.session_mode else 0

    # ------------------------------------------------------------------
    # Zoom / view helpers
    # ------------------------------------------------------------------

    def _view_rect_a(self):
        """View rectangle for panel A: (x1, y1, view_w, view_h) in original image coords."""
        h_a, w_a = self.img_a_orig.shape[:2]
        view_w = w_a / self.zoom_a
        view_h = h_a / self.zoom_a
        cx = w_a / 2 + self.pan_ax
        cy = h_a / 2 + self.pan_ay
        return cx - view_w / 2, cy - view_h / 2, view_w, view_h

    def _view_rect_b(self):
        """View rectangle for panel B: (x1, y1, view_w, view_h) in original image coords."""
        h_b, w_b = self.img_b_orig.shape[:2]
        view_w = w_b / self.zoom_b
        view_h = h_b / self.zoom_b
        cx = w_b / 2 + self.pan_bx
        cy = h_b / 2 + self.pan_by
        return cx - view_w / 2, cy - view_h / 2, view_w, view_h

    def _render_panel(self, img_orig, zoom, pan_x, pan_y):
        """Render a zoomed/panned panel to fixed display_width x disp_h size."""
        h, w = img_orig.shape[:2]
        view_w = w / zoom
        view_h = h / zoom
        cx = w / 2 + pan_x
        cy = h / 2 + pan_y
        x1 = cx - view_w / 2
        y1 = cy - view_h / 2
        x2 = x1 + view_w
        y2 = y1 + view_h

        # Clamp to image bounds
        x1c = max(0.0, x1)
        y1c = max(0.0, y1)
        x2c = min(float(w), x2)
        y2c = min(float(h), y2)

        # Gray background for out-of-bounds regions
        out = np.full((self.disp_h, self.display_width, 3), 48, dtype=np.uint8)

        if x1c < x2c and y1c < y2c:
            crop = img_orig[int(y1c):int(y2c), int(x1c):int(x2c)]
            if crop.size > 0:
                ox1 = int((x1c - x1) / view_w * self.display_width)
                oy1 = int((y1c - y1) / view_h * self.disp_h)
                ox2 = int((x2c - x1) / view_w * self.display_width)
                oy2 = int((y2c - y1) / view_h * self.disp_h)
                out_w = max(1, ox2 - ox1)
                out_h = max(1, oy2 - oy1)
                resized = cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
                out[oy1:oy1 + out_h, ox1:ox1 + out_w] = resized[:out_h, :out_w]

        return out

    # ------------------------------------------------------------------
    # Coordinate transforms (zoom-aware)
    # ------------------------------------------------------------------

    def pixel_to_orig_a(self, x_disp, y_disp):
        """Convert display panel-A coords to original image A coords."""
        x1, y1, view_w, view_h = self._view_rect_a()
        x_orig = x_disp / self.display_width * view_w + x1
        y_orig = y_disp / self.disp_h * view_h + y1
        return [x_orig, y_orig]

    def pixel_to_orig_b(self, x_disp, y_disp):
        """Convert display panel-B coords to original image B coords."""
        x1, y1, view_w, view_h = self._view_rect_b()
        x_orig = x_disp / self.display_width * view_w + x1
        y_orig = y_disp / self.disp_h * view_h + y1
        return [x_orig, y_orig]

    def orig_to_disp_a(self, x_orig, y_orig):
        """Convert original image A coords to canvas display coords."""
        x1, y1, view_w, view_h = self._view_rect_a()
        x_disp = int((x_orig - x1) / view_w * self.display_width)
        y_disp = int((y_orig - y1) / view_h * self.disp_h)
        return x_disp, y_disp

    def orig_to_disp_b(self, x_orig, y_orig):
        """Convert original image B coords to canvas display coords."""
        x1, y1, view_w, view_h = self._view_rect_b()
        x_disp = int((x_orig - x1) / view_w * self.display_width) + self.display_width + 5
        y_disp = int((y_orig - y1) / view_h * self.disp_h)
        return x_disp, y_disp
    
    def find_closest_point(self, x_disp, y_disp, radius_px=15):
        """Find closest pair within radius (in display pixels)."""
        best_idx = None
        best_dist = radius_px
        best_side = None
        
        for i, pair in enumerate(self.pairs):
            # Check point A
            x_a, y_a = self.orig_to_disp_a(pair['a'][0], pair['a'][1])
            dist_a = np.sqrt((x_a - x_disp)**2 + (y_a - y_disp)**2)
            if dist_a < best_dist:
                best_dist = dist_a
                best_idx = i
                best_side = 'a'
            
            # Check point B
            x_b, y_b = self.orig_to_disp_b(pair['b'][0], pair['b'][1])
            dist_b = np.sqrt((x_b - x_disp)**2 + (y_b - y_disp)**2)
            if dist_b < best_dist:
                best_dist = dist_b
                best_idx = i
                best_side = 'b'
        
        return best_idx, best_side
    
    def handle_click(self, x, y, button):
        """Handle mouse clicks (x,y in window coords)."""
        # Compensate for nav bar offset (session mode adds 40px at top)
        y = y - self.nav_offset

        if button == 1:  # Left click
            # Check for proximity to existing points first (for drag)
            idx, side = self.find_closest_point(x, y, radius_px=20)
            if idx is not None:
                # Click on existing point → prepare for drag
                self.selected_idx = idx
                self.selected_side = side
                self.drag_active = True
                print(f"  Selected pair #{idx+1} ({side}) for drag")
            else:
                # Click on empty space → start placing new point
                if self.point_in_image_a(x, y):
                    # Start point in A
                    self.pending_a = self.pixel_to_orig_a(x, y)
                    print(f"  Point A placed. Click on right image for point B.")
                else:
                    # Complete point in B (if pending_a exists)
                    if self.pending_a:
                        x_b_disp = x - (self.display_width + 5)
                        y_b_disp = y
                        point_b = self.pixel_to_orig_b(x_b_disp, y_b_disp)

                        pair = {'id': len(self.pairs), 'a': self.pending_a, 'b': point_b}
                        self.pairs.append(pair)
                        print(f"  Pair #{len(self.pairs)}: A{[round(v) for v in self.pending_a]} <-> B{[round(v) for v in point_b]}")
                        self.pending_a = None
                        self.dirty = True

        elif button == 3:  # Right click
            idx, side = self.find_closest_point(x, y, radius_px=20)
            if idx is not None:
                self.selected_idx = idx
                self.selected_side = side
                print(f"  Selected pair #{idx+1} ({side})")
            else:
                self.selected_idx = None
                self.selected_side = None
    
    def handle_drag(self, x, y):
        """Handle mouse drag – move selected point (x,y in window coords)."""
        # Compensate for nav bar offset
        y = y - self.nav_offset

        if not self.drag_active:
            return

        if self.selected_idx is not None and self.selected_side is not None:
            pair = self.pairs[self.selected_idx]

            if self.selected_side == 'a':
                if self.point_in_image_a(x, y):
                    pair['a'] = self.pixel_to_orig_a(x, y)
                    self.dirty = True
            else:  # 'b'
                if not self.point_in_image_a(x, y):
                    x_b_disp = x - (self.display_width + 5)
                    y_b_disp = y
                    pair['b'] = self.pixel_to_orig_b(x_b_disp, y_b_disp)
                    self.dirty = True

    def handle_zoom(self, x, y, zoom_in):
        """Zoom in/out centered on cursor position (x,y in window coords)."""
        y = y - self.nav_offset
        factor = 1.25 if zoom_in else 1 / 1.25
        in_panel_b = x > self.display_width + 5
        in_panel_a = x < self.display_width

        def apply_zoom(zoom_old, pan_x, pan_y, img_orig, x_local):
            h, w = img_orig.shape[:2]
            new_zoom = max(1.0, min(8.0, zoom_old * factor))
            if new_zoom == zoom_old:
                return zoom_old, pan_x, pan_y
            # Cursor in original image coords
            x1, y1, view_w, view_h = (lambda vr: vr)(
                (w / 2 + pan_x - w / (2 * zoom_old),
                 h / 2 + pan_y - h / (2 * zoom_old),
                 w / zoom_old, h / zoom_old))
            cx_orig = x_local / self.display_width * view_w + x1
            cy_orig = y / self.disp_h * view_h + y1
            # New view size
            new_view_w = w / new_zoom
            new_view_h = h / new_zoom
            # Keep cursor at same screen position → solve for new center
            new_x1 = cx_orig - (x_local / self.display_width) * new_view_w
            new_y1 = cy_orig - (y / self.disp_h) * new_view_h
            new_cx = new_x1 + new_view_w / 2
            new_cy = new_y1 + new_view_h / 2
            return new_zoom, new_cx - w / 2, new_cy - h / 2

        if in_panel_a:
            self.zoom_a, self.pan_ax, self.pan_ay = apply_zoom(
                self.zoom_a, self.pan_ax, self.pan_ay, self.img_a_orig, x)
        elif in_panel_b:
            x_local = x - (self.display_width + 5)
            self.zoom_b, self.pan_bx, self.pan_by = apply_zoom(
                self.zoom_b, self.pan_bx, self.pan_by, self.img_b_orig, x_local)

    def start_mid_drag(self, x, y):
        """Begin middle-button pan drag."""
        self.mid_drag_active = True
        self.mid_drag_start = (x, y - self.nav_offset)
        self.mid_drag_panel = 'a' if x < self.display_width else 'b'
        self.mid_drag_pan_start = (self.pan_ax, self.pan_ay, self.pan_bx, self.pan_by)

    def handle_mid_drag(self, x, y):
        """Pan view during middle-button drag."""
        if not self.mid_drag_active:
            return
        y_adj = y - self.nav_offset
        dx_screen = x - self.mid_drag_start[0]
        dy_screen = y_adj - self.mid_drag_start[1]

        if self.mid_drag_panel == 'a':
            h_a, w_a = self.img_a_orig.shape[:2]
            view_w = w_a / self.zoom_a
            view_h = h_a / self.zoom_a
            self.pan_ax = self.mid_drag_pan_start[0] - dx_screen / self.display_width * view_w
            self.pan_ay = self.mid_drag_pan_start[1] - dy_screen / self.disp_h * view_h
        else:
            h_b, w_b = self.img_b_orig.shape[:2]
            view_w = w_b / self.zoom_b
            view_h = h_b / self.zoom_b
            self.pan_bx = self.mid_drag_pan_start[2] - dx_screen / self.display_width * view_w
            self.pan_by = self.mid_drag_pan_start[3] - dy_screen / self.disp_h * view_h
    
    def handle_key(self, key):
        """Handle keyboard input."""
        if key == ord('s'):
            self.save_json()
        elif key == ord('u'):
            if self.pairs:
                removed = self.pairs.pop()
                print(f"  Undo: removed pair #{len(self.pairs)+1}")
                self.dirty = True
        elif key == ord('d') or key == 255:  # 255 = Delete key
            if self.selected_idx is not None:
                self.pairs.pop(self.selected_idx)
                print(f"  Deleted pair #{self.selected_idx+1}")
                self.selected_idx = None
                self.selected_side = None
                self.dirty = True
        elif key == ord('a'):
            # Auto-seed with confirmation if pairs exist
            if len(self.pairs) > 0:
                if not self.auto_seed_pending:
                    print(f"  WARNING: Will replace {len(self.pairs)} existing pairs. Press 'a' again to confirm.")
                    self.auto_seed_pending = True
                else:
                    self.auto_seed()
                    self.auto_seed_pending = False
            else:
                self.auto_seed()
                self.auto_seed_pending = False
        elif key == ord('r'):
            print("  Reset? Press 'r' again to confirm.")
            key2 = cv2.waitKey(1000)
            if key2 == ord('r'):
                self.pairs = []
                self.pending_a = None
                self.selected_idx = None
                print("  [OK] Reset.")
                self.dirty = True
        elif key == ord('l'):
            self.load_json()
        elif key == 27:  # Escape
            # Cancel pending point or deselect
            if self.pending_a is not None:
                self.pending_a = None
                print("  Cancelled pending point A")
            else:
                self.selected_idx = None
                self.selected_side = None
                print("  Deselected")
        elif key == ord('z') or key == ord('0'):
            # Reset zoom and pan for both panels
            self.zoom_a = 1.0
            self.pan_ax = 0.0
            self.pan_ay = 0.0
            self.zoom_b = 1.0
            self.pan_bx = 0.0
            self.pan_by = 0.0
            print("  Zoom reset")
        elif key == ord('n'):
            if self.session_mode:
                if self.dirty:
                    print("  Unsaved changes! Press 'n' again to move to next pair.")
                    key2 = cv2.waitKey(1000)
                    if key2 == ord('n'):
                        self.save_json()
                        self._init_session_pair_at_index(self.current_session_idx + 1)
                        print(f"  Moved to session pair {self.current_session_idx + 1}/{len(self.session_pairs)}")
                else:
                    if self.current_session_idx + 1 < len(self.session_pairs):
                        self._init_session_pair_at_index(self.current_session_idx + 1)
                        print(f"  Moved to session pair {self.current_session_idx + 1}/{len(self.session_pairs)}")
                    else:
                        print("  Already at last pair")
            return 'continue'
        elif key == ord('p'):
            if self.session_mode:
                if self.dirty:
                    print("  Unsaved changes! Press 'p' again to move to previous pair.")
                    key2 = cv2.waitKey(1000)
                    if key2 == ord('p'):
                        self.save_json()
                        self._init_session_pair_at_index(self.current_session_idx - 1)
                        print(f"  Moved to session pair {self.current_session_idx + 1}/{len(self.session_pairs)}")
                else:
                    if self.current_session_idx - 1 >= 0:
                        self._init_session_pair_at_index(self.current_session_idx - 1)
                        print(f"  Moved to session pair {self.current_session_idx + 1}/{len(self.session_pairs)}")
                    else:
                        print("  Already at first pair")
            return 'continue'
        elif key == ord('q'):
            if self.dirty:
                print("  Unsaved changes! Press 'q' again to quit without saving, or 's' to save.")
                key2 = cv2.waitKey(1000)
                if key2 == ord('q'):
                    return 'quit'
            else:
                return 'quit'
        
        return None
    
    def auto_seed(self):
        """Seed 30 semantic landmark pairs from MediaPipe."""
        print(f"  Auto-seeding landmarks from MediaPipe...")
        try:
            lm_a, _ = detect_landmarks(str(self.image_a_path))
            lm_b, _ = detect_landmarks(str(self.image_b_path))
            
            self.pairs = []
            for idx, lm_idx in enumerate(KEY_LANDMARK_INDICES):
                if lm_idx < len(lm_a) and lm_idx < len(lm_b):
                    pair = {
                        'id': idx,
                        'a': [float(lm_a[lm_idx, 0]), float(lm_a[lm_idx, 1])],
                        'b': [float(lm_b[lm_idx, 0]), float(lm_b[lm_idx, 1])],
                    }
                    self.pairs.append(pair)
            
            print(f"  [OK] Auto-seeded {len(self.pairs)} semantic points")
            self.pending_a = None
            self.selected_idx = None
            self.dirty = True
            self.auto_seed_pending = False  # Clear pending flag
        except Exception as e:
            print(f"  [ERROR] Auto-seed failed: {e}")
    
    def render(self):
        """Render display canvas with nav bar, help bar, points and status."""
        # Render panels (use pre-computed base image when at default view for performance)
        if self.zoom_a == 1.0 and self.pan_ax == 0.0 and self.pan_ay == 0.0:
            panel_a = self.img_a_disp
        else:
            panel_a = self._render_panel(self.img_a_orig, self.zoom_a, self.pan_ax, self.pan_ay)

        if self.zoom_b == 1.0 and self.pan_bx == 0.0 and self.pan_by == 0.0:
            panel_b = self.img_b_disp
        else:
            panel_b = self._render_panel(self.img_b_orig, self.zoom_b, self.pan_bx, self.pan_by)

        canvas = np.hstack([panel_a, self.separator, panel_b])

        # Draw completed pairs
        colors = [
            (0, 255, 0),      # green
            (0, 165, 255),    # orange
            (255, 0, 0),      # cyan
            (0, 255, 255),    # yellow
            (255, 0, 255),    # magenta
        ]

        for i, pair in enumerate(self.pairs):
            color = colors[i % len(colors)]
            if i == self.selected_idx:
                color = (0, 165, 255)  # orange for selected

            # Draw point A (with bounds-check)
            x_a, y_a = self.orig_to_disp_a(pair['a'][0], pair['a'][1])
            if 0 <= x_a < self.display_width and 0 <= y_a < self.disp_h:
                cv2.circle(canvas, (x_a, y_a), 8, color, -1)
                cv2.putText(canvas, str(i+1), (x_a-5, y_a+5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # Draw point B (with bounds-check)
            x_b, y_b = self.orig_to_disp_b(pair['b'][0], pair['b'][1])
            if self.display_width + 5 <= x_b < 2*self.display_width + 5 and 0 <= y_b < self.disp_h:
                cv2.circle(canvas, (x_b, y_b), 8, color, -1)
                cv2.putText(canvas, str(i+1), (x_b-5, y_b+5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Draw pending point A (blinking, with bounds-check)
        if self.pending_a is not None:
            if (self.frame_count // 8) % 2 == 0:
                x_a, y_a = self.orig_to_disp_a(self.pending_a[0], self.pending_a[1])
                if 0 <= x_a < self.display_width and 0 <= y_a < self.disp_h:
                    cv2.circle(canvas, (x_a, y_a), 8, (0, 255, 255), -1)  # yellow

        # Hover highlight: white ring around nearest point (with bounds-check)
        if self.hover_x >= 0 and self.hover_y >= 0:
            h_y = self.hover_y - self.nav_offset
            if 0 <= h_y < self.disp_h:
                h_idx, h_side = self.find_closest_point(self.hover_x, h_y, radius_px=25)
                if h_idx is not None:
                    pair = self.pairs[h_idx]
                    if h_side == 'a':
                        hx, hy = self.orig_to_disp_a(pair['a'][0], pair['a'][1])
                        if 0 <= hx < self.display_width and 0 <= hy < self.disp_h:
                            cv2.circle(canvas, (hx, hy), 13, (255, 255, 255), 2)
                    else:
                        hx, hy = self.orig_to_disp_b(pair['b'][0], pair['b'][1])
                        if self.display_width + 5 <= hx < 2*self.display_width + 5 and 0 <= hy < self.disp_h:
                            cv2.circle(canvas, (hx, hy), 13, (255, 255, 255), 2)

        # Nav bar (40px, session mode only) – prepend at top
        if self.session_mode:
            nav_bg = np.zeros((40, canvas.shape[1], 3), dtype=np.uint8)
            nav_text = (f"Pair {self.current_session_idx + 1}/{len(self.session_pairs)}: "
                        f"{self.image_a_path.name} <-> {self.image_b_path.name}  "
                        f"| p=Prev  n=Next")
            cv2.putText(nav_bg, nav_text, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 200, 255), 1)
            canvas = np.vstack([nav_bg, canvas])

        # Help bar
        help_bg = np.zeros((35, canvas.shape[1], 3), dtype=np.uint8)
        help_text = "LClick=Place RClick=Select Drag=Move  MidDrag=Pan  Ctrl+Scroll=Zoom  Esc=Cancel  z=ResetZoom  s=Save u=Undo d=Del a=AutoSeed(confirm!) r=Reset q=Quit"
        cv2.putText(help_bg, help_text, (6, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1)
        canvas = np.vstack([canvas, help_bg])

        # Status bar
        status_bg = np.zeros((25, canvas.shape[1], 3), dtype=np.uint8)
        status_text = f"Pairs: {len(self.pairs)}"
        if self.dirty:
            status_text += "  [*unsaved*]"
        if self.zoom_a != 1.0 or self.zoom_b != 1.0:
            status_text += f"   Zoom A:{self.zoom_a:.1f}x B:{self.zoom_b:.1f}x"
        cv2.putText(status_bg, status_text, (10, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        canvas = np.vstack([canvas, status_bg])

        self.frame_count += 1
        return canvas
    
    def run(self):
        """Main event loop."""
        if self.session_mode:
            window_name = f"Landmark Editor [Session] Pair {self.current_session_idx + 1}/{len(self.session_pairs)}: {self.image_a_path.name} <-> {self.image_b_path.name}"
        else:
            window_name = f"Landmark Editor: {self.image_a_path.name} <-> {self.image_b_path.name}"
        
        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
        cv2.moveWindow(window_name, 0, 0)  # Position at top-left corner
        
        # Mouse callback
        def mouse_callback(event, x, y, flags, userdata):
            if event == cv2.EVENT_LBUTTONDOWN:
                self.handle_click(x, y, 1)
            elif event == cv2.EVENT_RBUTTONDOWN:
                self.handle_click(x, y, 3)
            elif event == cv2.EVENT_MOUSEMOVE:
                self.hover_x = x
                self.hover_y = y
                if flags & cv2.EVENT_FLAG_LBUTTON:
                    self.handle_drag(x, y)
                elif self.mid_drag_active:
                    self.handle_mid_drag(x, y)
            elif event == cv2.EVENT_LBUTTONUP:
                self.drag_active = False
            elif event == cv2.EVENT_MBUTTONDOWN:
                self.start_mid_drag(x, y)
            elif event == cv2.EVENT_MBUTTONUP:
                self.mid_drag_active = False
            elif event == cv2.EVENT_MOUSEWHEEL:
                ctrl_held = bool(flags & cv2.EVENT_FLAG_CTRLKEY)
                if ctrl_held:
                    # Positive flags value = scroll up = zoom in
                    zoom_in = flags > 0
                    self.handle_zoom(x, y, zoom_in)
        
        cv2.setMouseCallback(window_name, mouse_callback)
        
        print(f"\n{'='*70}")
        if self.session_mode:
            print(f"Landmark Editor [Session Mode]")
            print(f"Pair {self.current_session_idx + 1}/{len(self.session_pairs)}: {self.image_a_path.name} <-> {self.image_b_path.name}")
        else:
            print(f"Landmark Editor: {self.image_a_path.name} <-> {self.image_b_path.name}")
        print(f"Output: {self.output_json}")
        print(f"{'='*70}")
        print("Instructions:")
        print("  Left-click left image → place point A")
        print("  Left-click right image → complete pair as point B")
        print("  Right-click → select point for editing")
        print("  Drag (when selected) → move point")
        print("  Delete/Backspace → delete selected pair")
        if self.session_mode:
            print("  p=Previous pair, n=Next pair")
        print("  s=Save, u=Undo, a=AutoSeed, r=Reset, l=Load, q=Quit")
        print(f"{'='*70}\n")
        
        while True:
            canvas = self.render()
            cv2.imshow(window_name, canvas)
            
            key = cv2.waitKey(30) & 0xFF
            if key != 255:  # 255 = no key pressed
                result = self.handle_key(key)
                if result == 'quit':
                    break
                elif result == 'continue':
                    continue
        
        cv2.destroyAllWindows()
        
        if self.dirty:
            print(f"\n[!] Unsaved changes to {self.output_json}")
        else:
            print(f"\n[OK] Final pairs: {len(self.pairs)}")


def main():
    parser = argparse.ArgumentParser(description='Interactive face correspondence point editor')
    parser.add_argument('--image-a', default=None, help='Path to source image (left)')
    parser.add_argument('--image-b', default=None, help='Path to target image (right)')
    parser.add_argument('--output', default=None, help='Output JSON path (default: landmarks/{stem_a}_{stem_b}.json)')
    parser.add_argument('--display-width', type=int, default=None, help='Display width per panel in pixels (default: auto-fit to ~800px height)')
    parser.add_argument('--session', default=None, help='Session JSON file with list of pairs to edit')
    
    args = parser.parse_args()
    
    try:
        if args.session:
            editor = LandmarkEditor(
                session_json=args.session,
                display_width=args.display_width
            )
        else:
            if not args.image_a or not args.image_b:
                parser.error("Either --session or both --image-a and --image-b are required")
            editor = LandmarkEditor(
                args.image_a, args.image_b,
                display_width=args.display_width,
                output_json=args.output
            )
        editor.run()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
