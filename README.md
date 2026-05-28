# Face Morpher

High-quality automated face morphing pipeline for portrait sequences. Seamlessly blend between multiple faces using advanced morphing algorithms (Delaunay, TPS, or Optical Flow).

## Features

- 🎭 **Multiple morphing backends**: Delaunay triangulation, Thin-Plate Splines (TPS), Optical Flow
- 🎬 **Complete pipeline**: Automatic landmark detection → interactive landmark editor → video rendering
- 🎚️ **Flexible timing**: Control transition duration, hold time, and frame rates
- 📐 **Manual control**: Interactive GUI editor for precise landmark placement
- 🚀 **Batch processing**: Handle multiple image sequences (sequential or all-pairs)
- 💾 **Session management**: Save/restore landmark editing sessions

## Quick Start

### Installation

```bash
# Clone or download the project
cd face_morpher

# Create virtual environment
python -m venv .venv
source .venv/Scripts/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

**One-liner (automatic pipeline):**
```bash
python pipeline.py --photos photos_nuevo --landmarks-dir landmarks_nuevo --output output/morph_nuevo.mp4
```

**Step-by-step:**
```bash
# 1. Interactive landmark editing (if needed)
python landmark_editor.py --image-a photos/image1.jpg --image-b photos/image2.jpg

# 2. Configure timing parameters
python timing_editor.py --load

# 3. Render morphing video
python morph.py --photos photos/ --width 1080 --height 1920 --profile final
```

## Timing Configuration

Control the animation speed and frame rates with three main parameters:

| Parameter | Range | Description |
|-----------|-------|-------------|
| **Duration** | 0.1 - 10.0 s | Transition time between images |
| **Hold** | 0.0 - 5.0 s | Static pause duration per image |
| **FPS** | 12 - 60 fps | Video frame rate |

### Configuration Methods

#### 1️⃣ **Interactive GUI** (Recommended)
```bash
python timing_editor.py --load
```
- Adjust sliders for Duration, Hold, and FPS
- Press `s` to save, `q` to quit
- Values saved to `morph_config.json`

#### 2️⃣ **Direct JSON Edit**
Edit `morph_config.json`:
```json
{
  "duration": 2.0,
  "hold": 0.8,
  "fps": 30
}
```

#### 3️⃣ **Command Line Arguments**
```bash
# Override timing directly
python morph.py --photos photos/ --duration 2.0 --hold 0.8 --fps 30 --width 1080 --height 1920
```

### Priority Order

If you specify timing in multiple ways, this is the precedence:

1. **CLI arguments** (highest)  
   `--fps 60 --duration 2.0 --hold 0.5`

2. **morph_config.json**  
   Values saved from timing editor

3. **Profile defaults** (lowest)  
   `preview` or `final`

### Frame Calculation

Total frames per cycle = (Duration + Hold) × FPS

**Example:** `duration=2.0s, hold=0.8s, fps=30`
- Transition frames: 2.0 × 30 = **60 frames**
- Hold frames: 0.8 × 30 = **24 frames**
- Total per pair: 84 frames ≈ **2.8 seconds**

### Preset Profiles

**Preview** (fast rendering):
```bash
python morph.py --photos photos/ --profile preview
# fps=24, duration=1.0, hold=0.5
```

**Final** (high quality):
```bash
python morph.py --photos photos/ --profile final
# fps=30, duration=2.0, hold=0.8
```

### Common Presets

| Use Case | Command |
|----------|---------|
| Quick preview | `--fps 24 --duration 1.0 --hold 0.4` |
| Smooth slow-mo | `--fps 60 --duration 2.0 --hold 0.8` |
| Cinema 24fps | `--fps 24 --duration 2.5 --hold 1.0` |
| Extra hold time | `--duration 2.0 --hold 3.0 --fps 30` |

## Landmark Editing

### Interactive Mode (Single Pair)

```bash
python landmark_editor.py --image-a photos/image1.jpg --image-b photos/image2.jpg
```

**Workflow:**
1. Press `A` to auto-seed with MediaPipe landmarks
2. Review point placement visually
3. Use `Ctrl + scroll` to zoom into problem areas
4. Click & drag points to adjust manually
5. Press `S` to save, `Q` to quit

### Batch Mode (Multiple Pairs)

```bash
python landmark_editor.py --session session.json
```

**Navigation:**
- `N` = next pair, `P` = previous pair
- `A` = auto-seed, `S` = save
- `R+R` = reset all, `D` = delete selected point
- `Z` or `0` = reset zoom

### Keyboard Reference

| Key | Action |
|-----|--------|
| `A` | Auto-seed: 30 MediaPipe landmarks |
| `S` | Save to JSON |
| `U` | Undo last point |
| `D` / `Delete` | Delete selected point |
| `R+R` | Reset all points (needs confirmation) |
| `L` | Reload from saved JSON |
| `Z` / `0` | Reset zoom to full view |
| `N` / `P` | Next/Previous pair (batch mode) |
| `Q` | Quit |

**Zoom & Pan:**
- `Ctrl + scroll` = zoom in/out
- `Middle mouse + drag` = pan

## Morphing Backends

### Delaunay Triangulation (Default)
```bash
python morph.py --photos photos/ --backend delaunay --profile final
```
- Uses landmark points to create triangular mesh
- Fast and reliable for most cases

### Thin-Plate Splines (TPS)
```bash
python morph.py --photos photos/ --backend tps --points-dir landmarks_nuevo --profile final
```
- Requires manual correspondence points (from landmark_editor)
- Smoother, more natural deformations
- Best quality for precise control

### Optical Flow
```bash
python morph.py --photos photos/ --backend opticalflow --profile final
```
- Motion-based morphing
- Useful when landmark detection is unreliable

## Output Options

```bash
# Custom resolution
python morph.py --photos photos/ --width 1920 --height 1080

# Custom output filename
python morph.py --photos photos/ --output my_morph.mp4

# Encoding quality (CRF: lower = better, 0-51)
python morph.py --photos photos/ --crf 17 --preset slow

# Sequential or all-pairs mode
python morph.py --photos photos/ --mode sequential
python morph.py --photos photos/ --mode all-pairs
```

## Full Pipeline Example

```bash
python pipeline.py \
  --photos photos_nuevo \
  --landmarks-dir landmarks_nuevo \
  --output output/morph_nuevo.mp4 \
  --backend tps \
  --profile final
```

This will:
1. Scan for images
2. Ask for morphing mode (sequential/all-pairs)
3. Check for missing landmark files
4. Open landmark editor for any missing pairs
5. Prompt for timing configuration
6. Render the final video

## Project Structure

```
face_morpher/
├── landmark_editor.py          # Interactive GUI for landmark placement
├── timing_editor.py            # GUI for animation timing
├── morph.py                    # Main rendering engine
├── pipeline.py                 # Orchestrates full workflow
├── detect.py                   # MediaPipe landmark detection
├── warp.py                     # Delaunay morphing backend
├── warp_tps.py                 # TPS morphing backend
├── warp_optical_flow.py        # Optical flow morphing backend
├── video_writer.py             # MP4 encoding
├── validate.py                 # Landmark quality checking
├── morph_config.json           # Timing parameters (auto-generated)
├── session.json                # Landmark editing sessions
├── landmarks/                  # Correspondence point JSON files
├── landmarks_nuevo/            # Alternative landmarks directory
├── photos/                     # Input images
├── photos_nuevo/               # Alternative input images
├── output/                     # Generated videos
└── LANDMARK_EDITOR_MANUAL.md   # Detailed landmark editor guide
```

## Documentation

- [**LANDMARK_EDITOR_MANUAL.md**](LANDMARK_EDITOR_MANUAL.md) — Complete guide for the interactive landmark editor, including keyboard shortcuts, zoom controls, and workflow tips

## Requirements

- Python 3.8+
- OpenCV (cv2)
- MediaPipe
- NumPy
- FFmpeg (for video encoding)

See `requirements.txt` for exact versions.

## Tips & Tricks

### Performance

- Use `--profile preview` for quick tests
- Use `--profile final` for high-quality output
- Reduce FPS for faster rendering
- Use `--width 540 --height 960` for preview

### Quality

- Press `A` in landmark editor to auto-seed before manual adjustment
- Use zoom (`Ctrl+scroll`) for precise landmark placement
- Enable cache: `python morph.py --cache-landmarks --use-cache`
- TPS backend generally produces smoother results

### Troubleshooting

**Landmarks don't load?**
```bash
python landmark_editor.py --image-a image1.jpg --image-b image2.jpg
# Manually place landmarks and save
```

**Morphing looks bad?**
- Check landmark alignment (zoom in landmark editor)
- Try different backend (`--backend opticalflow` or `--backend tps`)
- Adjust hold time (`--hold 1.0` for longer pauses)

**Video encoding fails?**
- Check output directory exists
- Ensure FFmpeg is installed
- Try different resolution (`--width 1080 --height 1920`)

## License

See LICENSE file for details.

---

**For detailed landmark editing instructions, see [LANDMARK_EDITOR_MANUAL.md](LANDMARK_EDITOR_MANUAL.md)**
