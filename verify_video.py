import cv2

vid = cv2.VideoCapture('output/test_directed.mp4')
frame_count = int(vid.get(cv2.CAP_PROP_FRAME_COUNT))
fps = vid.get(cv2.CAP_PROP_FPS)
duration = frame_count / fps if fps > 0 else 0
mins = int(duration // 60)
secs = int(duration % 60)
millisecs = int((duration % 1) * 1000)

print('✓ Video validated:')
print(f'  Frames: {frame_count}')
print(f'  FPS: {fps}')
print(f'  Duration: {mins}m {secs}s.{millisecs:03d}')
print(f'  Expected: 10020 frames, 167.0 seconds (2m 47s)')
match = 'YES' if frame_count == 10020 else 'NO'
print(f'  Match: {match}')
