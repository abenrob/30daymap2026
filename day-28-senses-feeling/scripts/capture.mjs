// Deterministic frame capture: node capture.mjs <outdir> [fps] [from] [to] [query]
import puppeteer from 'puppeteer-core';
import fs from 'fs';
const [out, fps = 30, from = 0, to = -1, query = ''] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: 'new',
  args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--font-render-hinting=none'] });
const page = await browser.newPage();
page.on('console', m => console.log('page:', m.text())); page.on('pageerror', e => console.log('ERR', e.message));
await page.setViewport({ width: 1080, height: 1350, deviceScaleFactor: 1 });
await page.goto(`http://localhost:8765/index.html?capture${query ? '&' + query : ''}`, { waitUntil: 'networkidle0', timeout: 120000 });
await page.waitForFunction('window.READY === true', { timeout: 120000 });
const dur = await page.evaluate('window.DURATION');
const times = String(from).includes(',') ? String(from).split(',').map(Number) : null;
const list = times ?? Array.from({ length: Math.round(((+to < 0 ? dur : +to) - +from) * fps) + 1 }, (_, i) => +from + i / fps);
const el = await page.$('#stage');
let k = 0;
for (const t of list) {
  await page.evaluate(t => window.renderAt(t), t);
  const name = times ? `t${t.toFixed(2)}` : String(Math.round(t * fps)).padStart(5, '0');
  await el.screenshot({ path: `${out}/${name}.png` });
  if (++k % 100 === 0) console.log(k, '/', list.length);
}
await browser.close();
