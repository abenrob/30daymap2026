"""Step 3: render the page frame by frame to a 4:5 MP4 (and the preview still).

    python3 scripts/03_render_video.py video  out.mp4 [first_frame last_frame]
    python3 scripts/03_render_video.py still  out.png [minute]

Serve the site folder first (python3 -m http.server 8765 from site/). The
page runs with ?capture&render: no buttons, and no clock of its own. For each
frame this script calls window.__renderFrame(ms), which draws that moment and
resolves once the basemap tiles have loaded, then takes a screenshot and pipes
it to ffmpeg. Frames are exact and never show half-loaded tiles.

Needs playwright and Chrome. Without a GPU it renders through SwiftShader at
about 1-3 s a frame; split the frame range across processes and join the
parts with ffmpeg -f concat to go faster.
"""
import asyncio
import subprocess
import sys
import time

from playwright.async_api import async_playwright

URL = "http://localhost:8765/day-24-network/?capture&render"
FPS = 30
VIDEO = (1080, 1350)      # 4:5 for LinkedIn
STILL = (1600, 900)       # landing-page card and og:image
CRF = 27                  # x264 quality: 27 is ~13 MB for the 36 s loop
CHROME_ARGS = ["--use-gl=angle", "--use-angle=swiftshader",
               "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]


async def open_page(p, size):
    browser = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=CHROME_ARGS)
    page = await browser.new_page(viewport={"width": size[0], "height": size[1]})
    await page.goto(URL, wait_until="load")
    # Ready once the graph has loaded (the loading message is removed).
    await page.wait_for_function(
        "window.__renderFrame && document.getElementById('loading') === null", timeout=120000)
    await page.evaluate("document.fonts.ready")
    return browser, page


async def render_video(out, first=None, last=None):
    async with async_playwright() as p:
        browser, page = await open_page(p, VIDEO)
        frames = int(await page.evaluate("window.__loop") / 1000 * FPS)
        first = 0 if first is None else first
        last = frames if last is None else last
        ffmpeg = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS),
             "-c:v", "png", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CRF),
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", out],
            stdin=subprocess.PIPE)
        # Warm up: the first draw builds the GPU buffers for every street.
        await page.evaluate("window.__renderFrame(0)")
        await page.wait_for_timeout(1500)
        started = time.time()
        for i in range(first, last):
            await page.evaluate(f"window.__renderFrame({i * 1000 / FPS})")
            ffmpeg.stdin.write(await page.screenshot(type="png"))
            if i % 60 == 0:
                print(f"frame {i}/{last}  {time.time() - started:.0f}s", flush=True)
        ffmpeg.stdin.close()
        ffmpeg.wait()
        await browser.close()
        print(f"done: {last - first} frames in {time.time() - started:.0f}s -> {out}")


async def render_still(out, minute):
    async with async_playwright() as p:
        browser, page = await open_page(p, STILL)
        intro, run = 1800, 30000                     # js/config.js introMs, runMs
        max_min = await page.evaluate("+document.getElementById('scrub').max") or 40
        ms = intro + min(1.0, minute / max_min) * run
        for _ in range(2):                           # second pass: camera settled
            await page.evaluate(f"window.__renderFrame({ms})")
            await page.wait_for_timeout(1500)
        await page.screenshot(path=out)
        await browser.close()
        print(f"still at minute {minute} -> {out}")


if __name__ == "__main__":
    mode, out, *rest = sys.argv[1:]
    if mode == "video":
        asyncio.run(render_video(out, *(int(x) for x in rest)))
    elif mode == "still":
        asyncio.run(render_still(out, float(rest[0]) if rest else 33))
    else:
        sys.exit(__doc__)
