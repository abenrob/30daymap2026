// Deterministic frame capture for the video.
// The page draws any moment with renderAt(t), so frames are rendered by stepping t = frame / FPS
// rather than recording playback: no dropped frames, and any range can be re-rendered.
//
// Usage: node 06_render_frames.js <explore.html url> <out dir> [first frame] [last frame]
// Then:  ffmpeg -framerate 30 -i frames/%05d.png -c:v libx264 -pix_fmt yuv420p -crf 18 -movflags +faststart day-09.mp4
const { chromium } = require('playwright');
const FPS = 30;
(async () => {
  const [,, url, out, f0 = '0', f1] = process.argv;
  // software WebGL so it runs on machines without a GPU
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1080, height: 1350 }, deviceScaleFactor: 1 });   // 4:5
  await p.goto(url + (url.includes('?') ? '&' : '?') + 'capture&t=0', { waitUntil: 'domcontentloaded', timeout: 120000 });
  // the page sets data-ready once every orthophoto tile is in and the fonts have loaded
  await p.waitForFunction(() => document.body.dataset.ready === '1', null, { timeout: 180000 });
  const D = await p.evaluate(() => window.DURATION);
  const last = f1 ? parseInt(f1) : Math.round(D * FPS);
  for (let f = parseInt(f0); f <= last; f++) {
    await p.evaluate((t) => window.renderAt(t), f / FPS);
    await p.screenshot({ path: `${out}/${String(f).padStart(5, '0')}.png` });
  }
  await b.close();
  console.log('frames', f0, 'to', last);
})();
