"""Caption the rendered frames and encode the MP4 (H.264, 4:5).

Caption per frame: km along the GR 7, ground height, km2 of ground in sight (from 12_frame_stats),
and a profile strip at the bottom: elevation (line) over ground in sight (amber bars), with the
walker's position. Holds the last frame for 2 s.

Run from the workspace root:
  python3 site/day-05-senses-sight/scripts/14_encode.py [--preview] [--fps 30]
Input : work/data/day-05-sight/renders/walk[_preview]/####.png, derived/walk_stats.json
Output: work/data/day-05-sight/renders/day-05-walk[_preview].mp4
ffmpeg: system ffmpeg, else the one bundled with pip's imageio-ffmpeg.
"""
import argparse, glob, json, os, shutil, subprocess, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont

p = argparse.ArgumentParser()
p.add_argument("--preview", action="store_true")
p.add_argument("--fps", type=float)
a = p.parse_args()

D = "work/data/day-05-sight"
src = f"{D}/renders/walk{'_preview' if a.preview else ''}"
files = sorted(glob.glob(f"{src}/[0-9][0-9][0-9][0-9].png"))
stats = json.load(open(f"{D}/derived/walk_stats.json"))["frames"]
st = {s["f"]: s for s in stats}
km = np.array([s["km"] for s in stats])
el = np.array([s["ground"] for s in stats])
vis = np.array([s["visible_km2"] for s in stats])
stride = (int(os.path.basename(files[1])[:4]) - int(os.path.basename(files[0])[:4])) if len(files) > 1 else 1
fps = a.fps or 30 / stride

def font(size, bold=False):
    for f in (["DejaVuSans-Bold.ttf", "DejaVuSans.ttf"][0 if bold else 1],):
        try:
            import matplotlib
            return ImageFont.truetype(os.path.join(matplotlib.get_data_path(), "fonts/ttf", f), size)
        except Exception:
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                return ImageFont.load_default()

ffmpeg = shutil.which("ffmpeg")
if not ffmpeg:
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

with tempfile.TemporaryDirectory() as tmp:
    for n, path in enumerate(files):
        f = int(os.path.basename(path)[:4]) - 1          # Blender numbers frames from 1
        s = st[f]
        im = Image.open(path).convert("RGB")
        Wd, Hd = im.size
        k = Wd / 1080                                    # layout drawn for 1080 wide
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        # top caption
        d.rectangle([0, 0, Wd, int(150 * k)], fill=(5, 7, 12, 170))
        d.text((int(48 * k), int(30 * k)), "GR 7 across the Mézenc massif", font=font(int(40 * k), True),
               fill=(235, 232, 225, 255))
        d.text((int(48 * k), int(88 * k)),
               f"km {s['km'] - km[0]:4.1f}   ·   {s['ground']:,} m   ·   {s['visible_km2']:,.0f} km² of ground in sight",
               font=font(int(30 * k)), fill=(255, 196, 120, 255))
        # profile strip
        top, bot = Hd - int(230 * k), Hd - int(60 * k)
        x0, x1 = int(48 * k), Wd - int(48 * k)
        d.rectangle([0, top - int(20 * k), Wd, Hd], fill=(5, 7, 12, 170))
        X = x0 + (km - km[0]) / (km[-1] - km[0]) * (x1 - x0)
        vb = vis / vis.max() * (bot - top) * 0.9
        for i in range(0, len(X), 2):                    # ground in sight, amber bars
            d.line([(X[i], bot), (X[i], bot - vb[i])], fill=(255, 176, 90, 120), width=max(1, int(2 * k)))
        ey = bot - (el - el.min()) / (el.max() - el.min()) * (bot - top) * 0.9
        d.line(list(zip(X, ey)), fill=(225, 230, 240, 230), width=max(1, int(3 * k)))
        i = f
        d.line([(X[i], top), (X[i], bot)], fill=(255, 255, 255, 140), width=max(1, int(2 * k)))
        r_ = int(9 * k)
        d.ellipse([X[i] - r_, ey[i] - r_, X[i] + r_, ey[i] + r_], fill=(255, 255, 255, 255))
        sf = font(int(20 * k))
        d.text((x0, bot + int(10 * k)), "elevation (line), ground in sight (bars)", font=sf, fill=(150, 156, 168, 255))
        cr = "Terrain IGN RGE ALTI · Trail © OpenStreetMap contributors"
        d.text((x1 - d.textlength(cr, font=sf), bot + int(10 * k)), cr, font=sf, fill=(150, 156, 168, 255))
        Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB").save(f"{tmp}/{n:04d}.png")
    last = f"{tmp}/{len(files) - 1:04d}.png"
    for j in range(int(2 * fps)):
        shutil.copy(last, f"{tmp}/{len(files) + j:04d}.png")
    out = f"{D}/renders/day-05-walk{'_preview' if a.preview else ''}.mp4"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", f"{tmp}/%04d.png",
                    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", out],
                   check=True)
print(f"{out}: {len(files)} frames at {fps:g} fps")
