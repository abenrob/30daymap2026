// Render the capture layout year by year with a controlled clock, one PNG per frame.
// node capture_frames.js URL OUTDIR [fps=30] [transitionMs=500] [holdMs=200] [startHoldMs=1500] [endHoldMs=3000]
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const [,, url, outdir, fpsA, trA, holdA, sHoldA, eHoldA] = process.argv;
  const fps = +(fpsA || 30), tr = +(trA || 500), hold = +(holdA || 200);
  const sHold = +(sHoldA || 1500), eHold = +(eHoldA || 3000);
  const dt = 1000 / fps;
  fs.mkdirSync(outdir, { recursive: true });
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1080, height: 1350 }, deviceScaleFactor: 1 });
  await p.clock.install();
  await p.goto(url, { waitUntil: 'networkidle' });
  for (let i = 0; i < 100 && !(await p.evaluate(() => window.__ready)); i++) await p.clock.runFor(100);
  await p.evaluate(() => document.fonts.ready);
  const years = await p.evaluate(() => { const s = document.getElementById('slider'); return [+s.min, +s.max]; });
  let n = 0;
  const snap = async () => { await p.screenshot({ path: `${outdir}/f${String(n++).padStart(5, '0')}.png` }); };
  await p.evaluate(y => window.__setYear(y, 0), years[0]);
  await p.clock.runFor(50);
  for (let t = 0; t < sHold; t += dt) await snap();
  for (let y = years[0] + 1; y <= years[1]; y++) {
    await p.evaluate(([y, tr]) => window.__setYear(y, tr), [y, tr]);
    for (let t = 0; t < tr + hold; t += dt) { await p.clock.runFor(dt); await snap(); }
  }
  await p.clock.runFor(100);
  for (let t = 0; t < eHold; t += dt) await snap();
  console.log('frames', n);
  await b.close();
})();
