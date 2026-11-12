// Frame renderer for the post video. Serve the site folder first, e.g.
//   cd site && python3 -m http.server 8812
//   node render.js frames/ [fromFrame] [toFrame]
//   ffmpeg -framerate 25 -i frames/%04d.png -c:v libx264 -pix_fmt yuv420p -crf 20 day12.mp4
// 540 x 675 CSS px at 2x = 1080 x 1350. Each frame sets the hour and the dash
// clock explicitly (window.__setFrame), so output does not depend on render
// speed. Two workers in parallel: node render.js frames 0 225 & node render.js frames 225
const { chromium } = require("playwright");
const fs = require("fs");

const FPS = 25;
// Segments: ["hold", hour, seconds] or ["ramp", fromHour, toHour, seconds].
// Hours are UTC hours since 25 Apr 00:00; ramps pass fractional hours, so the
// page eases flows between hourly values instead of stepping.
const PLAN = [
  ["hold", 78, 1.4],        // 08:00 CEST, 28 Apr
  ["ramp", 78, 82, 2.4],    // to the 12:00 hour
  ["ramp", 82, 83, 0.6],    // the collapse
  ["hold", 83, 2.2],        // 13:00, Spain at about 500 MW
  ["ramp", 83, 106, 11.5],  // restart, to 29 Apr 12:00 CEST
  ["hold", 106, 1.6],
];
const frames = [];
for (const seg of PLAN) {
  if (seg[0] === "hold") {
    for (let k = 0; k < Math.round(seg[2] * FPS); k++) frames.push(seg[1]);
  } else {
    const [, a, b, sec] = seg, n = Math.round(sec * FPS);
    for (let k = 0; k < n; k++) frames.push(a + ((b - a) * k) / n);
  }
}

(async () => {
  const [, , outDir = "frames", from = "0", to = "100000"] = process.argv;
  fs.mkdirSync(outDir, { recursive: true });
  const b = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const p = await b.newPage({ viewport: { width: 540, height: 675 }, deviceScaleFactor: 2 });
  await p.goto(`http://localhost:8812/day-12-power/?capture&h=${frames[0]}&t=0`);
  await p.waitForFunction(() => window.__ready === true, null, { timeout: 60000 });
  await p.waitForTimeout(1500);
  // Dash positions are integrated frame by frame, so a chunk that starts
  // mid-video first replays the earlier frames (no screenshots) to reach the
  // same state as a single run.
  await p.evaluate(([fr, n, fps]) => {
    for (let i = 0; i < n; i++) window.__setFrame(fr[i], i / fps);
  }, [frames, +from, FPS]);
  for (let i = +from; i < Math.min(frames.length, +to); i++) {
    await p.evaluate(([h, t]) => new Promise(r => {
      window.__setFrame(h, t);
      requestAnimationFrame(() => requestAnimationFrame(r));
    }), [frames[i], i / FPS]);
    await p.screenshot({ path: `${outDir}/${String(i).padStart(4, "0")}.png` });
  }
  console.log(`frames ${from}..${Math.min(frames.length, +to) - 1} of ${frames.length}`);
  await b.close();
})();
