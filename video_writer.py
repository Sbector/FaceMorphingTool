"""
Video writing using imageio-ffmpeg for H.264 MP4 output.
"""

import numpy as np
import imageio_ffmpeg as ifm
from pathlib import Path


def write_video(output_path, frame_iterator, size, fps=30, crf=18, preset='medium', codec='libx264'):
    """
    Write frames to H.264 MP4 file with configurable quality.
    
    Args:
        output_path: str or Path, output MP4 file path
        frame_iterator: Iterator yielding np.uint8 BGR frames
        size: tuple (width, height) of frames
        fps: int, frames per second
        crf: int, H.264 CRF (0-51; 0=lossless, 18-23=visually lossless, 28=default, 51=worst)
        preset: str, ffmpeg preset (ultrafast...veryslow; affects speed/compression)
        codec: str, ffmpeg codec name (default: libx264)
    
    Raises:
        ValueError: If frames have wrong shape/format
        IOError: If ffmpeg fails
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    w, h = size
    
    print(f"Writing video to {output_path}...")
    print(f"  Size: {w}x{h} @ {fps} fps")
    print(f"  Codec: {codec}, CRF {crf}, preset {preset}")
    
    try:
        # Build ffmpeg params for quality
        output_params = ['-crf', str(crf), '-preset', preset]
        
        writer = ifm.write_frames(
            str(output_path),
            size=size,
            pix_fmt_in='rgb24',      # Input: 3-byte RGB
            pix_fmt_out='yuv420p',   # H.264 standard chroma subsampling
            fps=fps,
            codec=codec,
            input_params=[],
            output_params=output_params,
        )
        
        writer.send(None)  # Prime generator
        
        frame_count = 0
        for frame_bgr in frame_iterator:
            # Validate frame
            if not isinstance(frame_bgr, np.ndarray):
                raise ValueError(f"Frame {frame_count}: Expected np.ndarray, got {type(frame_bgr)}")
            
            if frame_bgr.dtype != np.uint8:
                raise ValueError(f"Frame {frame_count}: Expected uint8, got {frame_bgr.dtype}")
            
            if frame_bgr.shape != (h, w, 3):
                raise ValueError(f"Frame {frame_count}: Expected shape {(h, w, 3)}, got {frame_bgr.shape}")
            
            # Convert BGR to RGB
            frame_rgb = frame_bgr[:, :, ::-1]  # Flip color channels
            
            # Send raw bytes to ffmpeg
            writer.send(frame_rgb.tobytes())
            frame_count += 1
            
            if frame_count % 30 == 0:
                print(f"  Wrote {frame_count} frames...", flush=True)
        
        writer.close()
        print(f"[OK] Video complete: {frame_count} frames written")
        
    except Exception as e:
        print(f"[ERROR] Error writing video: {e}")
        raise


def stream_frames_to_video(output_path, frame_generators, size, fps=30):
    """
    Convenience wrapper to chain multiple frame generators to video.
    
    Args:
        output_path: str or Path
        frame_generators: list of iterators, each yielding frames
        size: tuple (width, height)
        fps: int, frames per second
    
    Example:
        hold_frames_1 = [img_1] * 15  # 0.5s hold at 30 fps
        morph_frames_1_2 = generate_morph_frames(img_1, lm_1, img_2, lm_2, 60)
        hold_frames_2 = [img_2] * 15
        morph_frames_2_1 = generate_morph_frames(img_2, lm_2, img_1, lm_1, 60)
        
        write_video(
            "output.mp4",
            chain(hold_frames_1, morph_frames_1_2, hold_frames_2, morph_frames_2_1),
            size=(512, 512),
            fps=30
        )
    """
    from itertools import chain
    
    def combined_generator():
        for gen in frame_generators:
            for frame in gen:
                yield frame
    
    write_video(output_path, combined_generator(), size, fps)
