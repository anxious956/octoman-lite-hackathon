// node render.js --at 1,5.5,20      -> stills/t_*.jpg
// node render.js --out out.mp4      -> full render at 30 fps (optionally --from a --to b)
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const args = process.argv.slice(2);
const arg = (k, d) => { const i = args.indexOf(k); return i < 0 ? d : args[i + 1]; };
const FPS = 30;
(async () => {
  const take = JSON.parse(fs.readFileSync(path.join(__dirname, 'take/take.json')));
  const shots = require('./edit.js')(take);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  p.on('pageerror', (e) => console.error('page error', e.message));
  await p.goto('file://' + path.join(__dirname, 'comp.html'));
  await p.evaluate(() => document.fonts.ready);
  const total = await p.evaluate(([t, s]) => init(t, s), [take, shots]);
  let acc = 0; for (const s of shots) { console.log((acc).toFixed(2).padStart(7), s.kind, s.id || '', 'dur', s.dur.toFixed(2)); acc += s.dur; }
  console.log('total', total.toFixed(2), 's');
  for (const t of [0, 0.5, 1]) await p.evaluate((t) => seek(t), t);   // warm fonts and images
  const stage = p.locator('#stage');
  if (arg('--at')) {
    fs.mkdirSync(path.join(__dirname, 'stills'), { recursive: true });
    for (const t of arg('--at').split(',').map(Number)) {
      await p.evaluate((t) => seek(t), t);
      await p.screenshot({ path: path.join(__dirname, 'stills', `t_${t.toFixed(1).padStart(5, '0')}.jpg`), type: 'jpeg', quality: 88 });
    }
  } else {
    const out = arg('--out', 'out.mp4');
    const from = parseFloat(arg('--from', '0')), to = parseFloat(arg('--to', String(total)));
    const ff = spawn('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
      '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000', '-shortest',
      '-c:v', 'libx264', '-preset', 'slow', '-crf', '15', '-pix_fmt', 'yuv420p', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
      '-r', String(FPS), '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
    const n0 = Math.round(from * FPS), n1 = Math.round(to * FPS);
    const t0 = Date.now();
    for (let n = n0; n < n1; n++) {
      await p.evaluate((t) => seek(t), n / FPS);
      const buf = await p.screenshot({ type: 'jpeg', quality: 97 });
      if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
      if ((n - n0) % 150 === 0) console.log('frame', n - n0, '/', n1 - n0, ((Date.now() - t0) / 1000).toFixed(0) + 's');
    }
    ff.stdin.end();
    await new Promise((r) => ff.on('close', r));
    console.log('wrote', out);
  }
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
