// Deterministic frame render of the story map in capture mode: fake clock, one screenshot per frame.
const { chromium } = require('playwright');
const fs = require('fs');
// usage: node render.js <outdir> [query] [holdSeconds] [moveSeconds]
const OUT = process.argv[2], FPS = 30, QUERY = process.argv[3] || '', HOLD = Number(process.argv[4] || 3.6), MOVE = Number(process.argv[5] || 1.0), ONLY = null;
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 540, height: 675 }, deviceScaleFactor: 2 });
  await p.clock.install({ time: new Date('2026-11-11T12:00:00Z') });
  await p.goto(`http://localhost:8811/day-11-senses-sound/?capture${QUERY ? '&' + QUERY : ''}`, { waitUntil: 'networkidle' });
  await p.evaluate(() => document.fonts.ready);
  await p.evaluate(() => document.body.classList.add('frames'));
  await p.waitForTimeout(4000);
  await p.clock.pauseAt(new Date('2026-11-11T12:10:00Z'));
  const tops = await p.evaluate(() => [...document.querySelectorAll('.step')].map((e) => e.offsetTop));
  const dt = 1000 / FPS;
  let frame = 0, insetT = 0, lastStep = '0';
  async function settle() {
    for (let i = 0; i < 80; i++) {
      const ok = await p.evaluate(() => window.__map.areTilesLoaded() && window.__map.isStyleLoaded());
      if (ok) break;
      await p.waitForTimeout(50);
    }
  }
  async function shot(scrollY) {
    await p.evaluate((y) => window.scrollTo(0, y), scrollY);
    await p.clock.runFor(dt - 2);
    await p.waitForTimeout(15); // let IntersectionObserver deliver
    await settle();
    await p.clock.runFor(2);
    const step = await p.evaluate(() => document.querySelector('.step.active')?.dataset.step);
    if (step !== lastStep) { lastStep = step; insetT = 0; }
    insetT++;
    const k = Math.min(insetT / 12, 1);
    await p.evaluate((k) => { const el = document.getElementById('inset'); el.style.opacity = el.classList.contains('on') ? k : 0; el.style.transform = `rotate(-2.5deg) translateY(${(1 - k) * -12}px)`; }, k);
    await p.screenshot({ path: `${OUT}/f${String(frame).padStart(5, '0')}.jpg`, type: 'jpeg', quality: 92 });
    frame++;
  }
  const hold = async (y, s) => { for (let i = 0; i < Math.round(s * FPS); i++) await shot(y); };
  const move = async (y0, y1, s) => { const n = Math.round(s * FPS); for (let i = 1; i <= n; i++) await shot(y0 + (y1 - y0) * ease(i / n)); };
  const t0 = Date.now();
  await hold(tops[0], HOLD > 3 ? 3.0 : 2.4);
  const last = ONLY ?? tops.length - 1;
  for (let i = 1; i <= last; i++) {
    await move(tops[i - 1], tops[i], MOVE);
    await hold(tops[i], i === tops.length - 1 ? HOLD + 0.4 : HOLD);
    console.log(`section ${i}/${tops.length - 1} frames ${frame} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  await b.close();
})();
