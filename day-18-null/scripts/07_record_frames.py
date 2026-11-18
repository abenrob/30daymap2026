"""Step the page one frame at a time (0.4 simulated days per frame) and screenshot the 1080 x 1350 stage.

Usage: python 07_record_frames.py index.html frames/  [d3.min.js fonts.css]
The optional local d3 and font CSS are for machines without access to the CDNs.
Then:
  ffmpeg -framerate 30 -i frames/f%04d.png -c:v libx264 -crf 18 -pix_fmt yuv420p -movflags +faststart dahu.mp4
  ffmpeg -framerate 30 -i frames/f%04d.png -vf "fps=15,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=192:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" -loop 0 dahu.gif
"""
import asyncio, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

page, outdir = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
d3 = sys.argv[3] if len(sys.argv) > 3 else None
fonts = sys.argv[4] if len(sys.argv) > 4 else None

async def main():
    outdir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--allow-file-access-from-files"])
        pg = await b.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        if d3:
            await pg.route("**/d3.min.js", lambda r: r.fulfill(path=d3, content_type="application/javascript"))
        if fonts:
            await pg.route("**/fonts.googleapis.com/**", lambda r: r.fulfill(path=fonts, content_type="text/css"))
        await pg.goto(f"file://{page}#record")
        await pg.evaluate("window.__ready")
        stage = pg.locator("#stage")
        for i in range(int(365 / 0.4)):
            await pg.evaluate("window.__frame(0.4)")
            await stage.screenshot(path=str(outdir / f"f{i:04d}.png"))
        await b.close()

asyncio.run(main())
