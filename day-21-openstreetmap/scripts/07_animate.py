"""Render the animation -> renders/open_street_cheese_4x5.mp4 (1080 x 1350, 30 fps).

  python3 07_animate.py            full video (frames piped straight into ffmpeg, about 2 min)
  python3 07_animate.py --stills   a handful of PNG frames in renders/stills/ for review
"""
import os
import shutil
import subprocess
import sys
import tempfile

from config import H, RENDERS, W
import scene

os.makedirs(RENDERS, exist_ok=True)
print(len(scene.machines), 'machines on the map,', len(scene.SEGMENTS), 'cheeses,', len(scene.NO_AOP), 'without AOP')
print('order:', ', '.join(f"{s['title']} ({len(s['idx'])})" for s in scene.SEGMENTS))
print(f'duration {scene.TOTAL:.1f} s')

if '--stills' in sys.argv:
    out = os.path.join(RENDERS, 'stills')
    os.makedirs(out, exist_ok=True)
    picks = [('intro', 1.0)] + [(f'seg{k:02d}', t0 + 2.0) for k, t0 in enumerate(scene.TIMELINE)][::4] + \
            [('no_aop', scene.T_NO_AOP + 2.0), ('outro', scene.TOTAL - 1)]
    for name, t in picks:
        scene.render(t).convert('RGB').save(os.path.join(out, f'{name}.png'))
    print('stills ->', out)
    sys.exit()

# Encode to a local temp file first: the Mac folder mount does not allow ffmpeg's in-place writes reliably.
tmp = os.path.join(tempfile.gettempdir(), 'open_street_cheese_4x5.mp4')
ffmpeg = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                           '-s', f'{W}x{H}', '-r', str(scene.FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'veryfast',
                           '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', tmp], stdin=subprocess.PIPE)
for f in range(int(scene.TOTAL * scene.FPS)):
    ffmpeg.stdin.write(scene.render(f / scene.FPS).convert('RGB').tobytes())
ffmpeg.stdin.close()
ffmpeg.wait()
out = os.path.join(RENDERS, 'open_street_cheese_4x5.mp4')
shutil.copyfile(tmp, out)
print('video ->', out)
