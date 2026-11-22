"""Day 22 · Projections, step 5: the gallery card and social preview (1600 x 900).

The final globe of the video (the Blue Marble centred on Greenland) with every
projection's Greenland outline laid over it at the globe's scale: the photo is
the true shape, Mercator's outline is drawn in red. Title and day line on the
left. The card is laid out as a small HTML page and screenshotted.

    python 05_preview.py     # writes ../images/preview.png

Needs: what 04_record.py needs.
"""
import base64
import importlib
from pathlib import Path

from playwright.sync_api import sync_playwright

rec = importlib.import_module("04_record")  # the step-4 module (name starts with a digit)

HERE = Path(__file__).resolve().parent
OUT = HERE / ".." / "images" / "preview.png"
CARD_W, CARD_H = 1600, 900
GLOBE_CY = 770      # stage centre in page.js (CY)
CROP = 1080         # square crop around the globe, in frame pixels (globe and glow fit)

CARD = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; background: #000; }}
.card {{ position: relative; width: {w}px; height: {h}px; overflow: hidden; background: #000; }}
.globe {{ position: absolute; right: 20px; top: 0; width: {h}px; height: {h}px; }}
.text {{ position: absolute; left: 80px; top: 290px; width: 600px; color: #e9edf2; }}
.day {{ font: 500 26px "Inter", "Helvetica Neue", Helvetica, Arial, sans-serif; color: #8d97a3; margin-bottom: 18px; }}
.title {{ font: 700 60px Georgia, "Times New Roman", serif; line-height: 1.1; }}
.sub {{ font: 400 28px "Inter", "Helvetica Neue", Helvetica, Arial, sans-serif; color: #b7c0cb; margin-top: 26px; line-height: 1.4; }}
.sub b {{ color: #ff7a60; font-weight: 600; }}
</style></head><body><div class="card">
<img class="globe" src="data:image/png;base64,{img}">
<div class="text">
  <div class="day">#30DayMapChallenge · Day 22 · Projections</div>
  <div class="title">One Greenland, many Greenlands</div>
  <div class="sub">15 map projections at one scale, laid over the real thing. <b>Mercator</b> makes it 16× too big.</div>
</div></div></body></html>"""


if __name__ == "__main__":
    with sync_playwright() as p:
        browser, page = rec.open_page(p)
        # The final globe without text, the outlines on top, then a square crop around it.
        page.evaluate("drawCardFrame()")
        data = page.evaluate(
            f"""(() => {{
                const src = document.getElementById('c'), c = document.createElement('canvas');
                c.width = {CROP}; c.height = {CROP};
                c.getContext('2d').drawImage(src, (src.width - {CROP}) / 2, {GLOBE_CY} - {CROP} / 2, {CROP}, {CROP}, 0, 0, {CROP}, {CROP});
                return c.toDataURL('image/png').split(',')[1];
            }})()""")
        card = browser.new_page(viewport={"width": CARD_W, "height": CARD_H})
        card.set_content(CARD.format(w=CARD_W, h=CARD_H, img=data))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        card.locator(".card").screenshot(path=str(OUT))
        browser.close()
    print(f"wrote {OUT.resolve()}")
