// Records the live dashboard with a scripted browser. Output: frames/*.jpg + take.json (frame times, marks).
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const URL = 'https://d3gwyk02074rrp.cloudfront.net/';
const OUT = path.join(__dirname, 'take');
const VW = 1440, VH = 900, Z = 2; // page zoomed 2x in a 2880x2000 viewport: the screencast is then 2880x2000
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const now = () => Date.now() / 1000;

(async () => {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(path.join(OUT, 'frames'), { recursive: true });
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: VW * Z, height: VH * Z }, deviceScaleFactor: 1, timezoneId: 'America/Los_Angeles', locale: 'en-US' });
  await ctx.addInitScript(() => {
    const boot = () => {
      const st = document.createElement('style');
      st.textContent = `
        html { zoom: 2; }
        .foot { visibility: hidden !important; }
`;
      document.head.appendChild(st);
    };
    if (document.readyState === 'loading') addEventListener('DOMContentLoaded', boot); else boot();
  });
  const p = await ctx.newPage();
  const open = async () => { if (await p.$eval('#demo-panel', e => e.hidden)) { await p.click('#demo-open'); await sleep(300); } };
  const restock = async () => {
    await open(); await p.click('#restock'); await sleep(300); await p.click('#restock-yes');
    await p.waitForFunction(() => document.querySelectorAll('#orders .order').length === 0, null, { timeout: 20000 });
    await sleep(6000);
  };

  // ---- warm-up (off camera): one sale, one race, then restock ----
  await p.goto(URL, { waitUntil: 'networkidle' });
  await sleep(1000);
  await open(); await p.click('.story[data-scenario="sell"]');
  await p.waitForSelector('.state--sold', { timeout: 30000 });
  await sleep(1500);
  await open(); await p.click('.story[data-scenario="race"]');
  await p.waitForSelector('.order.is-blocked', { timeout: 30000 });
  await sleep(4000);
  await restock();
  await p.goto(URL, { waitUntil: 'networkidle' });
  await p.waitForSelector('#demo-panel:not([hidden])');
  await sleep(1500);
  console.log('warm-up done, recording');

  // ---- recording ----
  const cdp = await ctx.newCDPSession(p);
  const frames = []; const marks = {}; const info = {}; const mouse = []; const clicks = [];
  let n = 0;
  cdp.on('Page.screencastFrame', (f) => {
    const name = String(n++).padStart(6, '0') + '.jpg';
    fs.writeFile(path.join(OUT, 'frames', name), Buffer.from(f.data, 'base64'), () => {});
    frames.push([f.metadata.timestamp, name]);
    cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {});
  });
  const mark = (k) => { marks[k] = now(); console.log('mark', k); };
  let mx = 930, my = 600;
  await p.mouse.move(mx * Z, my * Z);
  const moveTo = async (x, y, ms = 900) => {
    const x0 = mx, y0 = my, t0 = Date.now();
    const bend = Math.min(60, Math.hypot(x - x0, y - y0) * 0.12);
    for (;;) {
      const u = Math.min(1, (Date.now() - t0) / ms);
      const e = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
      const arc = Math.sin(Math.PI * e) * bend;
      const cx = x0 + (x - x0) * e, cy = y0 + (y - y0) * e - arc;
      await p.mouse.move(cx * Z, cy * Z); mouse.push([now(), +cx.toFixed(1), +cy.toFixed(1)]);
      if (u >= 1) break;
      await sleep(8);
    }
    mx = x; my = y;
  };
  const center = async (sel) => { const r = await p.locator(sel).first().boundingBox(); return [(r.x + r.width / 2) / Z, (r.y + r.height / 2) / Z, r]; };
  const moveSel = async (sel, ms, dx = 0, dy = 0) => { const [x, y] = await center(sel); await moveTo(x + dx, y + dy, ms); };
  const boxes = async (sels) => { const o = {}; for (const q of sels) { const r = await p.locator(q).first().boundingBox(); if (r) o[q] = [r.x / Z, r.y / Z, r.width / Z, r.height / Z].map(v => Math.round(v)); } return o; };
  const click = async () => { clicks.push(now()); await p.mouse.down(); await sleep(70); await p.mouse.up(); };

  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 90, maxWidth: VW * Z, maxHeight: VH * Z, everyNthFrame: 1 });
  await sleep(300);
  mouse.push([now(), mx, my]);
  mark('start');
  await sleep(7000);                               // establishing shot + zoom on the shelf

  // --- race ---
  mark('race_move');
  await moveSel('.story[data-scenario="race"]', 1100, -40, 0);
  await sleep(1300);
  mark('race_click'); await click();
  await p.waitForSelector('#orders .order', { timeout: 30000 }); mark('race_orders');
  await p.waitForSelector('.order.is-blocked', { timeout: 30000 }); mark('race_blocked');
  await p.waitForSelector('.state--sold', { timeout: 30000 }); mark('race_sold');
  info.boxLive = await boxes(['.hero', '#shelf', '#shelf-core', '.flow', '#orders', '#alerts', '#demo-open']);
  info.race = await p.$$eval('#orders .order__btn', els => els.map(e => e.getAttribute('aria-label')));
  await sleep(4500);
  mark('blocked_move');
  await moveSel('.order.is-blocked .order__btn', 1000, -60, 0);
  await sleep(500);
  mark('blocked_click'); await click();
  await sleep(5500);

  // --- normal sale in Germany ---
  mark('sell_move');
  await moveSel('#demo-open', 1000);
  await sleep(300); await click(); mark('sell_panel');
  await sleep(700);
  await moveSel('.story[data-scenario="sell"]', 700, -40, 0);
  await sleep(1000);
  mark('sell_click'); await click();
  await moveTo(1180, 520, 900);                    // park the cursor away from the shelf
  await p.waitForFunction(() => { const f = document.querySelector('#orders .order'); return f && f.querySelector('.state--sold') && /Germany/.test(f.textContent); }, null, { timeout: 30000 });
  mark('sell_sold');
  await sleep(7000);

  // --- low stock ---
  mark('low_move');
  await moveSel('#demo-open', 900);
  await sleep(300); await click(); mark('low_panel');
  await sleep(700);
  await moveSel('.story[data-scenario="low"]', 700, -40, 0);
  await sleep(1000);
  mark('low_click'); await click();
  await moveTo(1180, 560, 900);
  await p.waitForFunction(() => /Keychain/.test(document.querySelector('#alerts').textContent), null, { timeout: 30000 });
  mark('low_alert');
  await sleep(7000);

  // --- how it works ---
  mark('how_move');
  await moveSel('#tab-how', 1000);
  await sleep(350);
  mark('how_click'); await click();
  await sleep(600);
  await moveTo(1320, 600, 900);
  info.boxHow = await boxes(['.arch', '.steps-table', '.how']);
  await sleep(9000);
  mark('end');
  await cdp.send('Page.stopScreencast');
  await sleep(500);

  info.boxes = {};
  fs.writeFileSync(path.join(OUT, 'take.json'), JSON.stringify({ vw: VW, vh: VH, z: Z, marks, info, mouse, clicks, frames }));
  console.log('frames', frames.length, 'seconds', (frames[frames.length - 1][0] - frames[0][0]).toFixed(1), JSON.stringify(info.race));

  // ---- leave the demo fresh for visitors ----
  await p.click('#tab-live'); await sleep(500);
  await restock();
  console.log('restocked');
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
