"""Day 22 · Projections, step 4: record the page to MP4, or grab review stills.

Opens ../index.html in headless Chromium, steps render(t) frame by frame at
30 fps and pipes each canvas frame (PNG) into ffmpeg (H.264, CRF 18, yuv420p).

    python 04_record.py                      # -> $D22_WORK/renders/day-22-projections.mp4
    python 04_record.py --stills 2 30 62     # -> $D22_WORK/stills/t002.00.png ...

Needs: playwright (pip install playwright; playwright install chromium), ffmpeg.
Set CHROME=/path/to/chrome to use an installed browser instead.
"""
import argparse
import base64
import os
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PAGE = (HERE / ".." / "index.html").resolve()
WORK = Path(os.environ.get("D22_WORK", HERE / ".." / ".." / ".." / "work" / "day-22-projections")).resolve()
FPS = 30
W, H = 1080, 1350


def open_page(p):
    """Load the page in record mode (no live loop, pixel ratio 1) and wait for the texture."""
    kw = {"executable_path": os.environ["CHROME"]} if os.environ.get("CHROME") else {}
    browser = p.chromium.launch(**kw)
    page = browser.new_page(viewport={"width": W, "height": H})
    page.add_init_script("window.__RECORD = true; window.__DPR = 1;")
    page.goto(PAGE.as_uri())
    page.evaluate("window.READY")
    return browser, page


def frame_png(page, t):
    """Render time t and return the canvas as PNG bytes."""
    data = page.evaluate(
        f"(renderAt({t}), document.getElementById('c').toDataURL('image/png').split(',')[1])")
    return base64.b64decode(data)


def record(page, out):
    total = page.evaluate("window.TOTAL")
    n = int(total * FPS) + 1
    out.parent.mkdir(parents=True, exist_ok=True)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS),
         "-c:v", "png", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE)
    for i in range(n):
        ff.stdin.write(frame_png(page, i / FPS))
    ff.stdin.close()
    ff.wait()
    print(f"wrote {out}: {n} frames, {total:.1f} s")


def stills(page, times):
    d = WORK / "stills"
    d.mkdir(parents=True, exist_ok=True)
    for t in times:
        f = d / f"t{t:06.2f}.png"
        f.write_bytes(frame_png(page, t))
        print(f"wrote {f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stills", nargs="+", type=float, metavar="T", help="save PNG stills at these times (s)")
    ap.add_argument("--out", type=Path, default=WORK / "renders" / "day-22-projections.mp4")
    args = ap.parse_args()
    with sync_playwright() as p:
        browser, page = open_page(p)
        if args.stills:
            stills(page, args.stills)
        else:
            record(page, args.out)
        browser.close()
