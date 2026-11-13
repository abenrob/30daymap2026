// Day 13 video: deterministic frame stepping. The animation is a pure function of t, so each
// frame is rendered on demand and screenshotted; the first half shows where residents work,
// the second half where workers come from.
//
// Usage (serve site/ with range support first: npx http-server -p 8013 -c-1):
//   node 04_render_video.cjs <INSEE code> <frames dir> [fps=24] [seconds=12]
//   ffmpeg -framerate 24 -i <frames dir>/f%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 \
//          -movflags +faststart out.mp4
// Frames are 540 x 675 CSS px at 2x = 1080 x 1350 (4:5). Existing frames are skipped, so an
// interrupted run can be resumed. Needs Playwright with Chromium; SwiftShader works headless.
const { chromium } = require('playwright');
const fs = require('fs');
const [,, code, outDir, fps = 24, secs = 12] = process.argv;
const N = fps * secs, CUT = N / 2, SPEED = 0.45;
fs.mkdirSync(outDir, { recursive: true });
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=swiftshader','--enable-webgl','--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 540, height: 675 }, deviceScaleFactor: 2 });
  p.on('pageerror', e => console.log('ERR '+e.message));
  await p.goto(`http://localhost:8013/day-13-interactions/?capture#${code}`, { waitUntil: 'load' });
  await p.waitForFunction(() => window.ready, null, { timeout: 150000 });
  await p.evaluate(() => document.fonts.ready);
  let dir = 0;
  for (let i = 0; i < N; i++) {
    const f = `${outDir}/f${String(i).padStart(4, '0')}.png`;
    const want = i < CUT ? 0 : 1;
    if (want !== dir) { await p.evaluate((d) => window.setDirection(d), want); await p.waitForTimeout(800); dir = want; }
    if (fs.existsSync(f)) continue;
    await p.evaluate((t) => window.renderAt(t), (i / fps) * SPEED);
    await p.waitForTimeout(30);
    await p.screenshot({ path: f });
    if (i % 24 === 0) console.log('frame', i, new Date().toISOString().slice(11, 19));
  }
  await b.close();
})();
