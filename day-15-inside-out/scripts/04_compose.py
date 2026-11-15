"""
Step 4: put the square Blender frames on a 4:5 post canvas (header + footer), then build the GIF / MP4.

    python 04_compose.py frames --out post --fps 10 --gif-width 800

Reads frames/frame_NNNN.png (square, from 03 with --aspect 1:1 --morph), writes post/frame_NNNN.png at
1080 x 1350, post/morph.gif (loops) and post/morph.mp4 when ffmpeg is on PATH.
The footer readout follows the same timeline as 03's MORPH_KEYS, so keep them in sync.
"""
import argparse
import math
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

MORPH_KEYS = ((1, 0.0), (15, 0.0), (60, 1.0), (90, 1.0), (135, 0.0), (150, 0.0))  # same as 03
W, H, SQ = 1080, 1350, 1080
HEAD_H = (H - SQ) // 2

BG = "#eef2f4"
INK = "#1b2a36"
MUTED = "#5d6f7c"
LAND = ["#c9bf93", "#a2ad66", "#8f8a5c", "#9a948c"]
SEA = ["#8fd6cb", "#3f93b3", "#17487a", "#0b2a52"]

FONT_PATHS = [
    "/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
BOLD_PATHS = [
    "/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf", "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def font(size, bold=False):
    for p in (BOLD_PATHS if bold else FONT_PATHS):
        if Path(p).exists():
            try:
                f = ImageFont.truetype(p, size, index=1 if (bold and p.endswith(".ttc")) else 0)
                return f
            except OSError:
                continue
    return ImageFont.load_default()


# The footer readout and the Canyon/Ridge headline are derived from the frame number, using the same timeline as 03.
def morph_value(frame):
    """0 = as it is, 1 = inverted. Smoothstep between keys approximates Blender's eased curve."""
    for (f0, v0), (f1, v1) in zip(MORPH_KEYS, MORPH_KEYS[1:]):
        if f0 <= frame <= f1:
            t = (frame - f0) / (f1 - f0)
            t = t * t * (3 - 2 * t)
            return v0 + (v1 - v0) * t
    return MORPH_KEYS[-1][1]


def text_w(d, s, f):
    return d.textlength(s, font=f)


def compose(frame_img, frame_no, titles, subtitle, credit):
    v = morph_value(frame_no)
    title = titles[0] if v < 0.5 else titles[1]
    mult = 1 - 2 * v  # elevation multiplier: +1 as it is, -1 inverted
    im = Image.new("RGB", (W, H), BG)
    im.paste(frame_img.convert("RGB").resize((SQ, SQ), Image.LANCZOS), (0, HEAD_H))
    d = ImageDraw.Draw(im)

    # header
    d.text((54, 28), title, font=font(46, True), fill=INK)
    d.text((54, 28 + 62), subtitle, font=font(24), fill=MUTED)

    # footer: readout + slider
    y0 = HEAD_H + SQ
    d.text((54, y0 + 14), f"Elevation \u00d7 {mult:+.2f}".replace("-", "\u2212"), font=font(34, True), fill=INK)
    state = "Land above the sea, seabed below" if v < 0.5 else "Seabed above the sea, land below"
    d.text((54, y0 + 58), state, font=font(24), fill=MUTED)

    # slider from +1 to -1
    sx0, sx1, sy = 640, W - 54, y0 + 30
    d.line((sx0, sy, sx1, sy), fill="#b7c4cc", width=6)
    zx = (sx0 + sx1) / 2
    d.line((zx, sy - 12, zx, sy + 12), fill="#8a9aa5", width=3)
    kx = sx0 + (sx1 - sx0) * v
    d.ellipse((kx - 13, sy - 13, kx + 13, sy + 13), fill=INK)
    small = font(20)
    d.text((sx0, sy + 18), "\u00d7 +1", font=small, fill=MUTED)
    lab = "\u00d7 \u22121"
    d.text((sx1 - text_w(d, lab, small), sy + 18), lab, font=small, fill=MUTED)

    # legend swatches (land / sea), small
    lx, ly = 640, y0 + 84
    for i, c in enumerate(LAND):
        d.rectangle((lx + i * 16, ly, lx + i * 16 + 16, ly + 14), fill=c)
    d.text((lx + 74, ly - 5), "land", font=small, fill=MUTED)
    lx2 = lx + 150
    for i, c in enumerate(SEA):
        d.rectangle((lx2 + i * 16, ly, lx2 + i * 16 + 16, ly + 14), fill=c)
    d.text((lx2 + 74, ly - 5), "sea", font=small, fill=MUTED)

    d.text((54, H - 32), credit, font=font(18), fill=MUTED)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", help="folder of frame_NNNN.png from 03")
    ap.add_argument("--out", default="post")
    ap.add_argument("--title-start", default="Monterey Canyon", help="headline while the terrain is as it is")
    ap.add_argument("--title-end", default="Monterey Ridge", help="headline once the terrain is inverted (switches at the flat midpoint)")
    ap.add_argument("--subtitle", default="Monterey Bay, California \u00b7 125 \u00d7 125 km \u00b7 vertical exaggeration 3\u00d7")
    ap.add_argument("--credit", default="Data: GMRT (Ryan et al. 2009), 100 m grid. Blender, GDAL.")
    ap.add_argument("--fps", type=float, default=30.0, help="playback fps of the MP4 (frames rendered every frame -> 30)")
    ap.add_argument("--gif-step", type=int, default=2, help="use every Nth frame in the GIF to keep it small (2 -> 15 fps)")
    ap.add_argument("--gif-width", type=int, default=800, help="GIF width in px (LinkedIn likes small files)")
    ap.add_argument("--colors", type=int, default=128)
    ap.add_argument("--mirror", action="store_true", help="frames cover the outbound half only: play them, hold, then play them in reverse")
    ap.add_argument("--hold-start", type=int, default=15, help="extra copies of the first frame (with --mirror)")
    ap.add_argument("--hold-end", type=int, default=20, help="extra copies of the last frame (with --mirror)")
    a = ap.parse_args()

    src = sorted(Path(a.frames).glob("frame_*.png"), key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)))
    if not src:
        raise SystemExit(f"no frame_*.png in {a.frames}")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    composed = []
    for p in src:
        n = int(re.search(r"(\d+)", p.stem).group(1))
        im = compose(Image.open(p), n, (a.title_start, a.title_end), a.subtitle, a.credit)
        im.save(out / p.name)
        composed.append(im)
    print(f"{len(composed)} frames -> {out}")
    if a.mirror:
        order = [composed[0]] * a.hold_start + composed + [composed[-1]] * a.hold_end + composed[-2:0:-1]
        seq = out / "seq"
        shutil.rmtree(seq, ignore_errors=True)
        seq.mkdir()
        for i, im in enumerate(order):
            im.save(seq / f"seq_{i:04d}.png")
        composed = order
        print(f"mirrored loop: {len(order)} frames")

    gw = a.gif_width
    gh = int(round(gw * H / W))
    gif_frames = composed[::max(1, a.gif_step)]
    small = [im.resize((gw, gh), Image.LANCZOS).quantize(colors=a.colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
             for im in gif_frames]
    gif = out / "morph.gif"
    small[0].save(gif, save_all=True, append_images=small[1:], duration=int(round(1000 * a.gif_step / a.fps)), loop=0, optimize=True, disposal=1)
    print(f"{gif}  {gif.stat().st_size / 1e6:.1f} MB ({gw}x{gh}, {len(small)} frames, {a.fps / a.gif_step:g} fps)")

    if shutil.which("ffmpeg"):
        mp4 = out / "morph.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", f"{a.fps:g}", "-pattern_type", "glob", "-i", str(out / ("seq/seq_*.png" if a.mirror else "frame_*.png")),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", "scale=1080:1350", str(mp4)], check=False)
        print(mp4 if mp4.exists() else "ffmpeg failed")
    else:
        print("ffmpeg not found: skipped MP4 (the GIF is done)")


if __name__ == "__main__":
    main()
