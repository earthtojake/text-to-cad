// Animated C, CAD and TEXTTOCAD marks: the block letters built on a CAD timeline (sketched on the
// grid, extruded, their openings cut, corners chamfered, then rendered) ending exactly on the
// static mark. Plain Node and SMIL; run after generate-logos.mjs, from any directory.
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import { blockGlyph, colors, light, depth, recession, letterLoops, lightFaces, logoArtwork, logoLayout, paintOrder, placement, shadowFilter } from './generate-logos.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const out = path.join(root, 'apps/docs/public/brand');
const edgeWidth = 0.038;
// Sketch ink: blue on the grid (white or charcoal), the edge navy on a face, amber for picked edges.
const ink = { line: '#249ddd', point: '#ffffff', accent: '#ffb347' };

const round = n => Number(n.toFixed(3));
const point = ([x, y]) => `${round(x)},${round(y)}`;
const same = (a, b) => Math.abs(a[0] - b[0]) < 1e-9 && Math.abs(a[1] - b[1]) < 1e-9;
const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
const recede = ([x, y], d) => [x + d * recession, y - d * recession];
const loopPath = points => `M${points.map(point).join('L')}Z`;
const facePath = (a, b, d) => loopPath([a, recede(a, d), recede(b, d), b]);
const length = points => points.reduce((sum, p, i) => sum + Math.hypot(...[0, 1].map(j => points[(i + 1) % points.length][j] - p[j])), 0);
const onSide = (p, [s, t]) => Math.abs((t[0] - s[0]) * (p[1] - s[1]) - (t[1] - s[1]) * (p[0] - s[0])) < 1e-9
  && [0, 1].every(j => Math.min(s[j], t[j]) - 1e-9 <= p[j] && p[j] <= Math.max(s[j], t[j]) + 1e-9);
// The edges of a loop that face the viewer, as in the static art: up, right, or up and right.
const visibleEdges = loop => loop.flatMap((a, j) => {
  const b = loop[(j + 1) % loop.length];
  return b[0] - a[0] + b[1] - a[1] > 0 ? [[a, b]] : [];
});
const behindFirst = (p, q) => p.order - q.order;
const order = (a, b) => (a[0] + b[0] - a[1] - b[1]) / 2;

// Corner points only: no closing repeat and no points along a straight run.
function corners(loop) {
  const points = loop.filter((p, i) => i === 0 || !same(p, loop[i - 1]));
  if (same(points[0], points.at(-1))) points.pop();
  return points.filter((b, i) => {
    const a = points.at(i - 1), c = points[(i + 1) % points.length];
    return Math.abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) > 1e-9;
  });
}

// How a piece is made. A, D and O get their 45° corners from a chamfer, so each diagonal edge
// starts as the square corner its axis-aligned neighbours meet at. Every opening is cut: the
// counters, and each run of the outline that leaves one side of the block and returns to it
// (C's and E's slots, A's foot, X's notches). A run from side to side (T's shoulders) is the
// letter's silhouette, sketched with the block. A rule is its own block, sketched outward from
// the word it flanks.
function features({ c, rule, side }) {
  const [w, h] = rule ?? [3, 4];
  const sides = [[[0, 0], [w, 0]], [[w, 0], [w, h]], [[w, h], [0, h]], [[0, h], [0, 0]]];
  const sharedSide = (p, q) => sides.some(s => onSide(p, s) && onSide(q, s));
  const [outline, ...counters] = rule ? [[[0, 0], [w, 0], [w, h], [0, h]]] : letterLoops(c).map(corners);
  const pre = [...outline];
  if ('ADO'.includes(c)) outline.forEach((a, i) => {
    const b = outline[(i + 1) % outline.length];
    if (a[0] === b[0] || a[1] === b[1]) return;
    pre[i] = pre[(i + 1) % outline.length] = outline.at(i - 1)[0] === a[0] ? [a[0], b[1]] : [b[0], a[1]];
  });
  const vertices = outline.map((post, i) => ({ pre: pre[i], post }));
  const square = pre.filter((p, j) => !same(p, pre.at(j - 1)));
  const n = square.length;
  const first = square.findIndex((p, j) => sharedSide(p, square[(j + 1) % n]));
  const block = [], slots = [];
  let run = [];
  for (let k = 0; k <= n; k++) {
    const a = square[(first + k) % n], b = square[(first + k + 1) % n];
    if (k < n && !sharedSide(a, b)) { run.push(a); continue; }
    if (run.length && sharedSide(run[0], a)) { slots.push([...run, a]); block.push(run[0]); }
    else block.push(...run);
    run = [];
    if (k < n) block.push(a);
  }
  const pen = side === 'left' ? [[w, 0], [0, 0], [0, h], [w, h]] : corners(block);
  return { vertices, square, counters, block: corners(block), pen, slots, cuts: [...slots, ...counters], chamfered: vertices.some(v => !same(v.pre, v.post)) };
}

const ease = { linear: '0 0 1 1', out: '0.2 0.7 0.3 1', inOut: '0.6 0 0.4 1', drag: '0.5 0 0.25 1', pop: '0.3 0 0.2 1' };

// One SMIL animation across the whole timeline from [seconds, value, easing into it] keys. It
// holds its first value before the first key and freezes on its last. The attribute's own value
// is the finished mark, which a renderer without SMIL shows.
function animate(attribute, keys, total, discrete = false) {
  const frames = [...keys];
  if (frames[0][0] > 0) frames.unshift([0, frames[0][1]]);
  if (frames.at(-1)[0] < total) frames.push([total, frames.at(-1)[1]]);
  const timing = `attributeName="${attribute}" dur="${round(total)}s" fill="freeze" keyTimes="${frames.map(([t]) => Number((t / total).toFixed(4))).join(';')}" values="${frames.map(f => f[1]).join(';')}"`;
  return discrete
    ? `<animate ${timing} calcMode="discrete"/>`
    : `<animate ${timing} calcMode="spline" keySplines="${frames.slice(1).map(f => ease[f[2] ?? 'linear']).join(';')}"/>`;
}

// Seconds for each step. Each word runs the steps in turn, starting a beat after the word before
// it, so the words overlap; within a step its letters start a beat apart, left to right. A step
// gives each letter its [start, end], or null for a letter it skips.
function timeline(letters, words) {
  const stagger = letters.length > 1 ? 0.04 : 0;
  const spans = { sketch: new Map(), extrude: new Map(), cutSketch: new Map(), cut: new Map(), select: new Map(), chamfer: new Map() };
  let first = 0, finish = 0;
  words.forEach((count, word) => {
    const members = Array.from({ length: count }, (_, k) => first + k);
    let cursor = word * 0.45;
    const step = (name, applies, seconds, pause) => {
      const order = members.filter(i => applies(letters[i]));
      if (!order.length) return;
      const start = cursor + pause;
      order.forEach((i, rank) => spans[name].set(i, [start + rank * stagger, start + rank * stagger + seconds]));
      cursor = start + (order.length - 1) * stagger + seconds;
    };
    step('sketch', () => true, 0.7, 0.2);
    step('extrude', () => true, 0.55, 0.1);
    step('cutSketch', l => l.cuts.length, 0.25, 0.1);
    step('cut', l => l.cuts.length, 0.4, 0.04);
    step('select', l => l.chamfered, 0.18, 0.08);
    step('chamfer', l => l.chamfered, 0.35, 0);
    finish = Math.max(finish, cursor);
    first += count;
  });
  const render = [finish + 0.2, finish + 0.65];
  return { ...Object.fromEntries(Object.entries(spans).map(([name, map]) => [name, i => map.get(i) ?? null])), render, total: render[1] + 0.02 };
}

function grid([left, top, width, height], rows, plan, id) {
  const lines = { minor: '', major: '' };
  for (let i = Math.ceil(left * 2); i <= (left + width) * 2; i++) lines[i % 2 ? 'minor' : 'major'] += `M${i / 2},${round(top)}V${round(top + height)}`;
  for (let i = Math.ceil(top * 2); i <= (top + height) * 2; i++) lines[i % 2 ? 'minor' : 'major'] += `M${round(left)},${i / 2}H${round(left + width)}`;
  const { total } = plan;
  const fade = animate('opacity', [[0, 0], [0.35, 1], [plan.render[0], 1], [plan.render[1], 0]], total);
  // Construction lines at each row's cap height and baseline, drawn across before the first stroke.
  const construction = rows.flat().map(y => `<line x1="${round(left)}" y1="${y}" x2="${round(left + width)}" y2="${y}" stroke="${ink.line}" stroke-width=".03" stroke-dasharray=".2 .12" stroke-opacity=".7">${animate('x2', [[0.05, round(left)], [0.5, round(left + width), 'inOut']], total)}</line>`).join('');
  return `<defs><radialGradient id="${id}-vignette" cx=".5" cy=".5" r=".5"><stop offset=".6" stop-color="#fff"/><stop offset="1" stop-color="#000"/></radialGradient>`
    + `<mask id="${id}-grid-mask" maskContentUnits="userSpaceOnUse"><rect x="${round(left)}" y="${round(top)}" width="${round(width)}" height="${round(height)}" fill="url(#${id}-vignette)"/></mask></defs>`
    + `<g opacity="0" mask="url(#${id}-grid-mask)">${fade}`
    + `<path d="${lines.minor}" stroke="${ink.line}" stroke-opacity=".12" stroke-width="1" vector-effect="non-scaling-stroke"/>`
    + `<path d="${lines.major}" stroke="${ink.line}" stroke-opacity=".24" stroke-width="1" vector-effect="non-scaling-stroke"/>`
    + `${construction}</g>`;
}

// A pen stroke round a closed loop, with sketch points dropped as it reaches each corner.
function sketchLoop(points, [start, end], total, { color, fill, fillOpacity, scale = 1 }) {
  const size = n => round(n / scale);
  const perimeter = length(points);
  let travelled = 0;
  const dots = points.map((p, i) => {
    const at = start + (travelled / perimeter) * (end - start);
    travelled += Math.hypot(points[(i + 1) % points.length][0] - p[0], points[(i + 1) % points.length][1] - p[1]);
    return `<circle cx="${round(p[0])}" cy="${round(p[1])}" r="${size(0.065)}" fill="${ink.point}" stroke="${color}" stroke-width="${size(0.03)}">${animate('r', [[at, 0], [at + 0.08, size(0.1), 'pop'], [at + 0.18, size(0.065), 'inOut']], total)}</circle>`;
  }).join('');
  const region = `<path d="${loopPath(points)}" fill="${fill}" fill-opacity="${fillOpacity}">${animate('fill-opacity', [[end, 0], [end + 0.2, fillOpacity, 'out']], total)}</path>`;
  const stroke = `<path d="${loopPath(points)}" fill="none" stroke="${color}" stroke-width="${size(0.05)}" stroke-linejoin="round" stroke-dasharray="${round(perimeter + 0.1)}" stroke-dashoffset="0">${animate('stroke-dashoffset', [[start, round(perimeter + 0.1)], [end, 0]], total)}</path>`;
  return region + stroke + dots;
}

function letterSketch(letter, i, plan) {
  const { total } = plan;
  const [, extrudeEnd] = plan.extrude(i);
  const visible = animate('opacity', [[plan.sketch(i)[0] - 0.01, 0], [plan.sketch(i)[0], 1], [extrudeEnd, 1], [extrudeEnd + 0.2, 0]], total);
  return `<g transform="${placement(letter)}" opacity="0">${visible}${sketchLoop(letter.pen, plan.sketch(i), total, { color: ink.line, fill: letter.palette.front, fillOpacity: 0.22, scale: letter.scale })}</g>`;
}

function letterModel(letter, i, plan) {
  const { vertices, square, counters, block, slots, cuts, palette, scale } = letter;
  const { total } = plan;
  const [extrudeStart, extrudeEnd] = plan.extrude(i);
  const size = n => round(n / scale);
  const edge = `stroke="${palette.edge}" stroke-width="${size(edgeWidth)}" stroke-linejoin="round"`;
  const fillOf = (a, b) => a[1] === b[1] ? palette.top : palette.side;
  const at = (v, t) => lerp(v.pre, v.post, t);
  const moves = v => !same(v.pre, v.post);
  const shown = (from, until) => animate('visibility', [[0, from ? 'hidden' : 'visible'], ...(from ? [[from, 'visible']] : []), ...(until ? [[until, 'hidden']] : [])], total, true);

  // The finished letter: its outline's visible faces, in the static art's order, so the build
  // hands over to the static mark pixel for pixel. letter() draws a block letter's top faces,
  // lowest first, then its sides, left to right; the rest go behind to front. A letter with
  // nothing to cut extrudes as it is; the chamfer slides corner points to 45° cuts.
  const staticOrder = letter.c && blockGlyph(letter.c)
    ? ({ a: p, b: q }, { a: r, b: s }) => {
      const flat = f => f[0].post[1] === f[1].post[1];
      const [pf, rf] = [flat([p, q]), flat([r, s])];
      if (pf !== rf) return pf ? -1 : 1;
      return pf ? r.post[1] - p.post[1] || Math.min(p.post[0], q.post[0]) - Math.min(r.post[0], s.post[0])
        : p.post[0] - r.post[0] || Math.min(p.post[1], q.post[1]) - Math.min(r.post[1], s.post[1]);
    }
    : behindFirst;
  const finished = extrudes => {
    const fixed = p => ({ pre: p, post: p });
    const faces = [vertices, ...counters.map(loop => loop.map(fixed))].flatMap(loop => loop.flatMap((a, j) => {
      const b = loop[(j + 1) % loop.length];
      return b.post[0] - a.post[0] + b.post[1] - a.post[1] > 0 ? [{ a, b, order: order(a.post, b.post), fill: fillOf(a.post, b.post) }] : [];
    })).sort(staticOrder).map(({ a, b, fill }) => {
      const shape = (d, t) => facePath(at(a, t), at(b, t), d);
      const keys = extrudes ? [[extrudeStart, shape(0, 0)], [extrudeEnd, shape(depth, 0), 'drag']] : [];
      if (letter.chamfered && (moves(a) || moves(b))) keys.push([plan.chamfer(i)[0], shape(depth, 0)], [plan.chamfer(i)[1], shape(depth, 1), 'inOut']);
      return `<path ${edge} fill="${fill}" d="${shape(depth, 1)}">${keys.length ? animate('d', keys, total) : ''}</path>`;
    }).join('');
    const front = t => loopPath(vertices.map(v => at(v, t))) + counters.map(loopPath).join('');
    const morph = letter.chamfered ? animate('d', [[plan.chamfer(i)[0], front(0)], [plan.chamfer(i)[1], front(1), 'inOut']], total) : '';
    return `${faces}<path ${edge} fill="${palette.front}" fill-rule="evenodd" d="${front(1)}">${morph}</path>`;
  };

  let body;
  if (!cuts.length) body = finished(true);
  else {
    const [sketchStart, sketchEnd] = plan.cutSketch(i);
    const [cutStart, cutEnd] = plan.cut(i);
    const sweep = (shape, ease = 'inOut') => animate('d', [[cutStart, shape(0)], [cutEnd, shape(depth), ease]], total);
    // The block extrudes first.
    const blockFaces = visibleEdges(block).map(([a, b]) => ({ a, b, order: order(a, b) })).sort(behindFirst)
      .map(({ a, b }) => `<path ${edge} fill="${fillOf(a, b)}" d="${facePath(a, b, depth)}">${animate('d', [[extrudeStart, facePath(a, b, 0)], [extrudeEnd, facePath(a, b, depth), 'drag']], total)}</path>`).join('');
    // Cut to depth c, the part is the cut profile in front of c and the whole block behind it:
    // the block's face at c is the pocket floor, a block side keeps a notch to c where a slot
    // opens through it, and each new wall runs from the front face back to c.
    const floor = c => loopPath(block.map(p => recede(p, c)));
    const blockSides = block.map((p, j) => [p, block[(j + 1) % block.length]]);
    const notched = (a, b) => {
      const gaps = slots.filter(s => onSide(s[0], [a, b]) && onSide(s.at(-1), [a, b]))
        .map(s => [s[0], s.at(-1)]).sort((p, q) => Math.hypot(p[0][0] - a[0], p[0][1] - a[1]) - Math.hypot(q[0][0] - a[0], q[0][1] - a[1]));
      return c => loopPath([a, ...gaps.flatMap(([p, q]) => [p, recede(p, c), recede(q, c), q]), b, recede(b, depth), recede(a, depth)]);
    };
    const cutFaces = [
      ...visibleEdges(block).map(([a, b]) => ({ shape: notched(a, b), order: order(a, b), fill: fillOf(a, b) })),
      ...[square, ...counters].flatMap(visibleEdges).filter(([a, b]) => !blockSides.some(side => onSide(a, side) && onSide(b, side)))
        .map(([a, b]) => ({ shape: c => facePath(a, b, c), order: order(a, b), fill: fillOf(a, b) })),
    ].sort(behindFirst).map(({ shape, fill }) => `<path ${edge} fill="${fill}" d="${shape(depth)}">${shape(0) === shape(depth) ? '' : sweep(shape)}</path>`).join('');
    body = `<g visibility="hidden">${shown(0, cutStart)}${blockFaces}<path ${edge} fill="${palette.front}" d="${loopPath(block)}"/></g>`
      + `<g visibility="hidden">${shown(cutStart, cutEnd)}<path ${edge} fill="${palette.front}" d="${floor(depth)}">${sweep(floor)}</path>${cutFaces}`
      + `<path ${edge} fill="${palette.front}" fill-rule="evenodd" d="${loopPath(square)}${counters.map(loopPath).join('')}"/></g>`
      // Through: the floor reaches the back and the finished letter takes over.
      + `<g>${shown(cutEnd)}${finished(false)}</g>`
      // The openings, sketched on the front face just before the cut.
      + `<g opacity="0">${animate('opacity', [[sketchStart - 0.01, 0], [sketchStart, 1], [cutStart + 0.05, 1], [cutStart + 0.25, 0]], total)}${cuts.map(loop => sketchLoop(loop, [sketchStart, sketchEnd], total, { color: palette.edge, fill: palette.edge, fillOpacity: 0.2, scale })).join('')}</g>`;
  }

  if (letter.chamfered) {
    // Chamfer: the corner edges are picked, then the 45° cut grows from each corner.
    const [selectStart, selectEnd] = plan.select(i);
    const [chamferStart, chamferEnd] = plan.chamfer(i);
    const picks = [], previews = [];
    vertices.forEach((a, j) => {
      const b = vertices[(j + 1) % vertices.length];
      if (!moves(a) || !moves(b) || !same(a.pre, b.pre)) return;
      const corner = a.pre;
      // The corner's depth edge shows unless it runs behind the letter's own front face.
      const probe = recede(corner, 0.05);
      const hidden = probe[0] > 0 && probe[0] < 3 && probe[1] > 0 && probe[1] < 4;
      if (!hidden) picks.push(`M${point(corner)}L${point(recede(corner, depth))}`);
      const line = t => `M${point(at(a, t))}L${point(at(b, t))}`;
      previews.push(`<path d="${line(1)}" fill="none" stroke="${ink.accent}" stroke-width="${size(0.07)}" stroke-linecap="round">${animate('d', [[chamferStart, line(0)], [chamferEnd, line(1), 'inOut']], total)}</path>`);
      const dx = b.post[0] - a.post[0], dy = b.post[1] - a.post[1];
      if (dx + dy > 0) {
        const shape = t => facePath(at(a, t), at(b, t), depth);
        previews.unshift(`<path d="${shape(1)}" fill="${ink.accent}" stroke="${palette.edge}" stroke-width="${size(edgeWidth)}" stroke-linejoin="round">${animate('d', [[chamferStart, shape(0)], [chamferEnd, shape(1), 'inOut']], total)}</path>`);
      }
    });
    // The previews switch off when the feature commits; amber fading over blue turns khaki.
    body += `<path d="${picks.join('')}" fill="none" stroke="${ink.accent}" stroke-width="${size(0.1)}" stroke-linecap="round" visibility="hidden">${animate('opacity', [[selectStart, 0], [selectEnd, 1, 'out']], total)}${animate('visibility', [[0, 'visible'], [chamferStart + 0.1, 'hidden']], total, true)}</path>`
      + `<g visibility="hidden">${shown(chamferStart, chamferEnd + 0.1)}${previews.join('')}</g>`;
  }
  // The extrusion is a translucent preview until it reaches full depth.
  const preview = animate('opacity', [[extrudeStart, 0], [extrudeStart + 0.08, 0.55], [extrudeEnd, 0.55], [extrudeEnd + 0.15, 1]], total);
  return `<g transform="${placement(letter)}">${preview}${body}</g>`;
}

// `lighter`, `words` and `stacked` are logoArtwork's: the letters drawn in the lighter blue
// (TEXTTOCAD's "TO"), the letters in each word, which start their builds a beat apart, and the
// stacked lockup.
export function animatedLogoSvg(text, { standalone = false, lighter = [], words = [text.length], stacked = false } = {}) {
  const id = `build-${text.toLowerCase()}${stacked ? '-stacked' : ''}`;
  const { box, label, title, artwork } = logoArtwork(text, { standalone, lighter, words, stacked, id });
  const layout = logoLayout(text, { words, stacked, lighter });
  // The pieces in reading order, which the timeline follows; the drawing follows paint order.
  const letters = layout.pieces.map((piece, index) => ({ ...piece, index, palette: piece.lighter ? light : colors, ...features(piece) }));
  const counts = letters.reduce((tally, { word }) => { tally[word] = (tally[word] ?? 0) + 1; return tally; }, []);
  const plan = timeline(letters, counts);
  const { total } = plan;
  // The pieces are built lit and shadowed exactly as the finished mark, with its gradients,
  // highlights and contact shadow, so finishing changes nothing: the grid fades out and the
  // static artwork takes over from the identical build.
  const { shaded, clips } = lightFaces(paintOrder(letters).map(l => letterModel(l, l.index, plan)).join(''), id, `${id}-build-highlight`);
  const model = `<defs>${shadowFilter(`${id}-build-shadow`)}${clips.join('')}</defs>`
    // Opacity, not visibility, hides it: a hidden group still draws any child that is visible.
    + `<g opacity="0" filter="url(#${id}-build-shadow)">${animate('opacity', [[0, 1], [plan.render[1], 0]], total, true)}${shaded}</g>`;
  const sketches = letters.map((l, i) => letterSketch(l, i, plan)).join('');
  const rendered = `<g>${animate('visibility', [[0, 'hidden'], [plan.render[1], 'visible']], total, true)}${artwork}</g>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${box.join(' ')}" role="img" aria-label="${label}"><title>${title}</title>${grid(box, layout.rows, plan, id)}${model}${sketches}${rendered}</svg>\n`;
}

// Each static mark in apps/docs/public/brand and the word it builds; `<name>-animated.svg` is its build.
export const marks = [
  ['logo-c', 'C', { standalone: true }],
  ['logo-cad', 'CAD', {}],
  ['logo-texttocad', 'TEXTTOCAD', { lighter: [4, 5], words: [4, 2, 3] }],
  ['logo-texttocad-stacked', 'TEXTTOCAD', { lighter: [4, 5], words: [4, 2, 3], stacked: true }],
];

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  await mkdir(out, { recursive: true });
  for (const [name, text, options] of marks) {
    await writeFile(path.join(out, `${name}-animated.svg`), animatedLogoSvg(text, options));
  }
  console.log('Generated the animated C, CAD, TEXTTOCAD and stacked TEXT TO CAD marks.');
}
