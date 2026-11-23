# Day 24 video: frame-by-frame capture of the page (index.html?capture&render)
# with headless Chrome (playwright, SwiftShader WebGL), piped to ffmpeg.
# Serve the page first (e.g. python3 -m http.server 8765 from this day folder;
# render.html was index.html with local copies of deck.gl, maplibre and the
# IBM Plex fonts). Run two halves in parallel and concat:
#   python3 render.py part1.mp4 0 537 & python3 render.py part2.mp4 537 1074
# 1,074 frames (35.8 s at 30 fps), about 25 min on 2 CPUs.
import asyncio, sys, subprocess, time
from playwright.async_api import async_playwright
FPS = 30
async def main():
    out = sys.argv[1]
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome",
            args=["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader","--ignore-gpu-blocklist"])
        pg = await b.new_page(viewport={"width":1080,"height":1350})
        await pg.goto("http://localhost:8765/index.html?capture&render", wait_until="load")
        await pg.wait_for_function("window.__renderFrame && document.getElementById('loading') === null", timeout=120000)
        await pg.evaluate("document.fonts.ready")
        loop = await pg.evaluate("window.__loop")
        n = int(loop / 1000 * FPS)
        f0 = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        f1 = int(sys.argv[3]) if len(sys.argv) > 3 else n
        ff = subprocess.Popen(["ffmpeg","-y","-loglevel","error","-f","image2pipe","-framerate",str(FPS),"-c:v","png","-i","-",
              "-c:v","libx264","-preset","veryfast","-crf","18","-pix_fmt","yuv420p","-movflags","+faststart",out], stdin=subprocess.PIPE)
        await pg.evaluate("window.__renderFrame(0)"); await pg.wait_for_timeout(1500)
        t = time.time()
        for i in range(f0, f1):
            await pg.evaluate(f"window.__renderFrame({i * 1000 / FPS})")
            ff.stdin.write(await pg.screenshot(type="png"))
            if i % 60 == 0: print(f"frame {i}/{f1}  {time.time()-t:.0f}s", flush=True)
        ff.stdin.close(); ff.wait(); await b.close()
        print(f"done {f1-f0} frames in {time.time()-t:.0f}s -> {out}")
asyncio.run(main())
