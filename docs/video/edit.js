// The edit: which part of the take plays when, where the camera looks, and the captions.
// Times inside a clip are seconds from the start of that clip; L(mark, off) converts a mark of the take.
module.exports = function buildShots(take) {
  const m = take.marks;
  const WIDE = [720, 470, 1300];      // shelf, order strip and live orders
  const TOP = [720, 349, 1240];       // top of the page: shelf and order strip
  const PANEL = [1065, 610, 750];
  const FULL = [720, 495, 1440];      // whole width, down to the demo button     // the "Try the demo" panel in the corner
  const clip = (from, to, extra, build) => {
    const src0 = from, dur = to - from + (extra || 0);
    const L = (mark, off = 0) => m[mark] + off - src0;
    const s = { kind: 'clip', dur, time: [[0, src0], [to - from, to]] };
    Object.assign(s, build(L, dur));
    return s;
  };
  const shots = [];

  shots.push({ kind: 'card', id: 'hook', dur: 9.7, fadeIn: 0.3, fadeOut: 0.4 });
  shots.push({ kind: 'card', id: 'logo', dur: 4.8, fadeIn: 0.4, fadeOut: 0.4 });

  // 1. the race for the last unit
  shots.push(clip(m.start + 0.3, m.sell_move - 0.2, 0, (L) => ({
    fadeIn: 0.5,
    chip: ['01', 'The race for the last unit', 4.2],
    cam: [
      [0, 720, 405, 1440], [2.9, 720, 405, 1440], [4.3, ...TOP], [L('race_move', -0.1), ...TOP],
      [L('race_move', 1.0), ...PANEL], [L('race_click', 0.25), ...PANEL], [L('race_click', 1.35), ...WIDE],
      [L('race_sold', 1.3), ...WIDE], [L('race_sold', 2.5), 474, 600, 860], [L('blocked_click', -0.2), 474, 600, 860],
      [L('blocked_click', 1.0), ...WIDE],
    ],
    caps: [
      [0.5, 3.6, 'One shelf of stock. <b>Four stores</b> in four countries.'],
      [3.9, L('race_move', -0.1), 'Only <b class="warn">1 unit left</b>, and every store offers it.'],
      [L('race_move', 0.1), L('race_click', 0.8), 'Two customers. Two countries. <b>The same instant.</b>'],
      [L('race_click', 1.0), L('race_sold', 0.2), 'Both orders reach the API at once…'],
      [L('race_sold', 0.4), L('blocked_click', 0.0), '<b class="ok">One sold.</b> <b class="bad">One blocked.</b> The last unit sells exactly once.'],
      [L('blocked_click', 0.5), L('sell_move', -0.5), 'It stopped at the shelf check: <b>one atomic DynamoDB transaction.</b>'],
    ],
    rings: [
      [4.5, L('race_move', -0.3), 550, 142, 340, 137, '#f1a33c'],
      [L('race_sold', 2.6), L('blocked_move', 0.9), 125, 505, 698, 98, '#e5484d'],
      [L('race_sold', 3.0), L('blocked_move', 0.9), 125, 609, 698, 80, '#2f9e5f'],
    ],
  })));

  // 2. a normal sale
  shots.push(clip(m.sell_move - 0.2, m.low_move - 0.2, 0, (L) => ({
    chip: ['02', 'A normal sale', 3.6],
    cam: [
      [0, ...WIDE], [0.2, ...WIDE], [1.2, ...FULL], [L('sell_panel', 0.2), ...FULL], [L('sell_panel', 1.2), ...PANEL], [L('sell_click', 0.25), ...PANEL], [L('sell_click', 1.3), ...TOP],
    ],
    caps: [
      [0.5, L('sell_click', 0.5), 'Now a normal sale: a customer in <b>Germany</b> buys one.'],
      [L('sell_click', 0.8), L('sell_sold', 2.4), 'The shelf drops, and <b>Step Functions</b> updates every store in parallel.'],
      [L('sell_sold', 2.7), L('low_move', -0.5), '<b>Lambda</b> converts € to $ at today’s ECB rate. The receipt goes to <b>S3</b>.'],
    ],
  })));

  // 3. low stock
  shots.push(clip(m.low_move - 0.2, m.low_alert + 5.6, 0, (L, dur) => ({
    chip: ['03', 'Running low', 3.6],
    cam: [
      [0, ...TOP], [0.2, ...TOP], [1.2, ...FULL], [L('low_panel', 0.2), ...FULL], [L('low_panel', 1.2), ...PANEL], [L('low_click', 0.25), ...PANEL], [L('low_click', 1.3), ...WIDE],
    ],
    caps: [
      [0.5, L('low_click', 0.5), 'One more sale takes this product <b class="warn">below its warning level…</b>'],
      [L('low_click', 0.9), dur - 0.3, '…so the workflow raises a <b class="warn">low-stock alert</b>, straight into DynamoDB.'],
    ],
  })));

  // 4. how it works
  shots.push(clip(m.how_move - 0.2, m.end - 0.1, 2.2, (L, dur) => ({
    fadeOut: 0.5,
    chip: ['04', 'Under the hood', 3.8],
    cam: [
      [0, ...WIDE], [L('how_click', 0.1), ...WIDE], [L('how_click', 1.2), ...TOP], [L('how_click', 5.4), ...TOP], [L('how_click', 6.7), 652, 551, 1240],
    ],
    caps: [
      [L('how_click', 0.9), L('how_click', 5.6), 'API Gateway → Lambda → <b>Step Functions</b> → DynamoDB → S3'],
      [L('how_click', 6.3), dur - 0.6, 'No servers. No pipeline. Scales to zero. One <code>sam deploy</code>.'],
    ],
  })));

  shots.push({ kind: 'card', id: 'cta', dur: 9.5, fadeIn: 0.5, fadeOut: 0.7 });
  return shots;
};
