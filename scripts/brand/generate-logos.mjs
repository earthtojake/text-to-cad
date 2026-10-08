// Deterministic vector branding. Run from any directory with Node; no renderer required.
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const out = path.join(root, 'apps/docs/public/brand');
export const depth = 2;
export const recession = 0.42; // Upright front and receding 45° edges, following the supplied sketch.
export const colors = { front: '#249ddd', top: '#62b7ec', side: '#1475ad', edge: '#123e59' };
// The lighter blue that sets "TO" apart in TEXTTOCAD. It keeps the brand edge
// color and shades its sides toward the brand blue, so it reads as the same material.
export const light = { front: '#8fd3f5', top: '#bce5f9', side: '#4b9fcd', edge: colors.edge };
export const gap = 0.5; // Between letters; each letter's extrusion tucks behind the next.
// Most glyphs use half-unit coordinates. T centers a 1.5-unit stem.
// All letters stay three units wide and four tall.
const glyphs = {
  C: ['111111', '111111', '111111', '111000', '111000', '111111', '111111', '111111'],
  T: ['111111111111', '111111111111', '111111111111', '000111111000', '000111111000', '000111111000', '000111111000', '000111111000'],
  E: ['111111', '111111', '111000', '111111', '111111', '111000', '111111', '111111'],
};
// Straight 45-degree cuts on X, A's top, D's right and O's four corners.
// Counters remain square; no glyph contains curved profile segments.
const chamferProfiles = {
  // A solid body with a 45° V-notch in each side: half a unit deep at top and bottom, 0.75 at the sides.
  X: [[0,0],[1,0],[1.5,0.5],[2,0],[3,0],[3,1.25],[2.25,2],[3,2.75],[3,4],[2,4],[1.5,3.5],[1,4],[0,4],[0,2.75],[0.75,2],[0,1.25],[0,0]],
  A: [[0,0.5],[0.5,0],[2.5,0],[3,0.5],[3,4],[2,4],[2,3.5],[1,3.5],[1,4],[0,4],[0,0.5]],
  D: [[0,0],[2.5,0],[3,0.5],[3,3.5],[2.5,4],[0,4],[0,0]],
  O: [[0,0.5],[0.5,0],[2.5,0],[3,0.5],[3,3.5],[2.5,4],[0.5,4],[0,3.5],[0,0.5]],
};
// A, D and O share one opening: a one-unit square centered on the letter.
const counter = [[1,1.5],[1,2.5],[2,2.5],[2,1.5],[1,1.5]];
const counters = { A: counter, D: counter, O: counter };
const round = n => Number(n.toFixed(3));
const point = ([x, y]) => `${round(x)},${round(y)}`;
const key = (x, y) => `${x},${y}`;

// Cancel shared edges and trace the remaining outlines, including counters.
// One front path has no internal grid seams at small sizes.
function outline(rows, rowHeight, columnWidth) {
  const edges = new Map();
  rows.forEach((row, y) => [...row].forEach((cell, x) => {
    if (cell !== '1') return;
    const vertices = [[x,y], [x+1,y], [x+1,y+1], [x,y+1]];
    vertices.forEach((a, i) => {
      const b = vertices[(i+1)%4];
      const forward = `${a}:${b}`, reverse = `${b}:${a}`;
      if (edges.has(reverse)) edges.delete(reverse);
      else edges.set(forward, [a,b]);
    });
  }));
  const loops = [];
  while (edges.size) {
    const [firstKey, [start, next]] = edges.entries().next().value;
    edges.delete(firstKey);
    let current = next;
    const loop = [start, current];
    while (key(...current) !== key(...start)) {
      const entry = [...edges].find(([, [a]]) => key(...a) === key(...current));
      if (!entry) throw new Error('Open glyph outline');
      edges.delete(entry[0]);
      current = entry[1][1];
      loop.push(current);
    }
    loops.push(`M${loop.map(([x, y]) => point([x * columnWidth, y * rowHeight])).join('L')}Z`);
  }
  return loops.join('');
}

function letter(rows, place, height, palette, edgeWidth) {
  const edge = palette.edge ? ` stroke="${palette.edge}" stroke-width="${edgeWidth}" stroke-linejoin="round"` : '';
  const rowHeight = height / rows.length;
  const columnWidth = 3 / rows[0].length;
  const shift = depth * recession;
  const front = (x, y) => point([x * columnWidth, y * rowHeight]);
  const back = (x, y) => point([x * columnWidth + shift, y * rowHeight - shift]);
  const faces = [];
  const filled = (u, v) => rows[v]?.[u] === '1';
  // Merge exposed coplanar faces into maximal runs; no decorative cube grid.
  for (let y = rows.length - 1; y >= 0; y--) {
    for (let u = 0; u < rows[0].length; u++) {
      if (!filled(u,y) || filled(u,y-1)) continue;
      const start = u;
      while (filled(u+1,y) && !filled(u+1,y-1)) u++;
      faces.push(`<path${edge} fill="${palette.top}" d="M${front(start,y)}L${back(start,y)}L${back(u+1,y)}L${front(u+1,y)}Z"/>`);
    }
  }
  for (let u = 0; u < rows[0].length; u++) {
    for (let y = 0; y < rows.length; y++) {
      if (!filled(u,y) || filled(u+1,y)) continue;
      const start = y;
      while (filled(u,y+1) && !filled(u+1,y+1)) y++;
      faces.push(`<path${edge} fill="${palette.side}" d="M${front(u+1,start)}L${back(u+1,start)}L${back(u+1,y+1)}L${front(u+1,y+1)}Z"/>`);
    }
  }
  return `<g transform="${place}">${faces.join('')}<path${edge} fill="${palette.front}" fill-rule="evenodd" d="${outline(rows, rowHeight, columnWidth)}"/></g>`;
}

function chamferLetter(vertices, counter, place, palette, edgeWidth) {
  const shift = depth * recession;
  const edge = palette.edge ? ` stroke="${palette.edge}" stroke-width="${edgeWidth}" stroke-linejoin="round"` : '';
  const back = p => [p[0] + shift, p[1] - shift];
  const outline = points => `M${points.map(point).join('L')}Z`;
  const loops = counter ? [vertices, counter] : [vertices];
  const faces = [];
  for (const loop of loops) {
    for (let i = 1; i < loop.length; i++) {
      const a = loop[i-1], b = loop[i];
      if (b[0] - a[0] + b[1] - a[1] <= 0) continue;
      const fill = a[1] === b[1] ? palette.top : palette.side;
      const path = outline([a, back(a), back(b), b]);
      faces.push({ order: (a[0] + b[0] - a[1] - b[1]) / 2, svg: `<path${edge} fill="${fill}" d="${path}"/>` });
    }
  }
  faces.sort((a, b) => a.order - b.order);
  return `<g transform="${place}">${faces.map(f => f.svg).join('')}<path${edge} fill="${palette.front}" fill-rule="evenodd" d="${loops.map(outline).join('')}"/></g>`;
}

// Half-unit grids change stroke weight without changing the 3 × 4 silhouette
// bounds or the two-unit extrusion. Bold is the selected production shape.
function cRows(shape) {
  if (shape === 'bold') return glyphs.C;
  if (shape === 'original') return ['111', '100', '100', '111'];
  const weights = { spine: [1.5, 1], arms: [1, 1.5], bold: [1.5, 1.5] }[shape];
  if (!weights) throw new Error(`Unknown C shape: ${shape}`);
  const [spine, arms] = weights;
  return Array.from({ length: 8 }, (_, y) => Array.from({ length: 6 }, (_, x) =>
    y < arms * 2 || y >= 8 - arms * 2 || x < spine * 2 ? '1' : '0').join(''));
}

// The selected Soft relief treatment: gently lit blue faces, inset edge
// highlights and a small contact shadow. Geometry stays identical to flat art.
// Gradient stops per face for each palette, keyed by the flat face color they replace.
const relief = [
  { suffix: '', faces: colors, highlight: '#d1f1ff', front: ['#39b0e9', '#249ddd', '#1785bf'], top: ['#94d9fa', '#51ade1'], side: ['#258cc5', '#0b5887'] },
  { suffix: '-light', faces: light, highlight: '#ebf7fd', front: ['#9ad7f6', '#8fd3f5', '#81bedd'], top: ['#d3eefb', '#b3daed'], side: ['#59a7d1', '#38779a'] },
];

// The contact shadow under the whole mark; the animation casts the same one while it builds.
export function shadowFilter(id) {
  return `<filter id="${id}" x="-30%" y="-40%" width="170%" height="200%" color-interpolation-filters="sRGB"><feDropShadow dx=".035" dy=".10" stdDeviation=".075" flood-color="#082f4a" flood-opacity=".22"/></filter>`;
}

// Light flat faces as Soft relief: each face's flat color becomes its gradient (the
// `${id}...` gradients softRelief defines), and a front or top face gains an inset highlight
// clipped to it. A face's animations, and its visibility, carry over to its highlight and clip,
// so a build is lit exactly as the finished mark.
export function lightFaces(body, id, clipPrefix = `${id}-highlight`) {
  const clips = [];
  const shaded = body.replace(/<path([^>]*?)(?:\/>|>((?:<animate\b[^>]*\/>)*)<\/path>)/g, (original, attrs, animations = '') => {
    const fill = attrs.match(/fill="([^"]+)"/)?.[1];
    const palette = relief.find(({ faces }) => [faces.front, faces.top, faces.side].includes(fill));
    if (!palette) return original;
    const face = ['front', 'top', 'side'].find(f => palette.faces[f] === fill);
    const close = animations ? `>${animations}</path>` : '/>';
    let result = `<path${attrs.replace(`fill="${fill}"`, `fill="url(#${id}${palette.suffix}-${face})"`)}${close}`;
    if (face !== 'side') {
      const d = attrs.match(/ d="([^"]+)"/)[1];
      const visibility = attrs.match(/ visibility="[^"]+"/)?.[0] ?? '';
      const clip = `${clipPrefix}-${clips.length}`;
      clips.push(`<clipPath id="${clip}"><path d="${d}" clip-rule="evenodd"${visibility}${close}</clipPath>`);
      result += `<g clip-path="url(#${clip})"><path d="${d}" fill="none" stroke="${palette.highlight}" stroke-opacity="${face === 'top' ? '.6' : '.38'}" stroke-width=".037" transform="translate(.042 .042)"${visibility}${close}</g>`;
    }
    return result;
  });
  return { shaded, clips };
}

function softRelief(body, id) {
  const { shaded, clips } = lightFaces(body, id);
  const defs = [
    ...relief.flatMap(({ suffix, front, top, side }) => [
      `<linearGradient id="${id}${suffix}-front" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="2" y2="4"><stop stop-color="${front[0]}"/><stop offset=".5" stop-color="${front[1]}"/><stop offset="1" stop-color="${front[2]}"/></linearGradient>`,
      `<linearGradient id="${id}${suffix}-top" gradientUnits="userSpaceOnUse" x1="0" y1="-1" x2="3" y2="4"><stop stop-color="${top[0]}"/><stop offset="1" stop-color="${top[1]}"/></linearGradient>`,
      `<linearGradient id="${id}${suffix}-side" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="4" y2="3"><stop stop-color="${side[0]}"/><stop offset="1" stop-color="${side[1]}"/></linearGradient>`,
    ].filter(() => suffix === '' || body.includes(light.front))),
    shadowFilter(`${id}-shadow`),
    ...clips,
  ];
  return `<defs>${defs.join('')}</defs><g filter="url(#${id}-shadow)">${shaded}</g>`;
}

// The stacked lockup's middle word: half-size letters a block apart, between long rules.
const small = 0.5;
// Clear space between stacked rows, above each row's receding top faces.
const rowGap = 0.33;
const rule = { height: 0.5, gap: 0.75 };

// Where each piece of a mark sits, in reading order: a letter `c`, or a `rule` bar [width,
// height] in its own block units, at (x, y), drawn at `scale`, in word `word` and row `row`.
// `words` counts each word's letters. A mark is one row; `stacked` sets three words as a film
// title does: the first, then the middle word small between two long rules, then the last, the
// first and last scaled to one width. `height` bounds the front faces; `rows` gives each row's
// top and bottom.
export function logoLayout(text, { words = [text.length], stacked = false, lighter = [] } = {}) {
  const letters = [...text].map((c, i) => ({ c, lighter: lighter.includes(i) }));
  const split = words.map((count, w) => letters.splice(0, count).map(l => ({ ...l, word: w })));
  const span = (count, scale = 1, spacing = gap) => count * 3 * scale + (count - 1) * spacing;
  const row = (word, left, top, scale = 1, spacing = gap, index = 0) =>
    word.map((l, k) => ({ ...l, x: left + k * (3 * scale + spacing), y: top, scale, row: index }));
  if (!stacked) return { pieces: row(split.flat(), 0, 0), words: split.map(w => w.map(l => l.c).join('')), height: 4, rows: [[0, 4]] };
  const [first, middle, last] = split;
  const width = Math.max(span(first.length), span(last.length));
  const firstScale = width / span(first.length), lastScale = width / span(last.length);
  const firstBottom = 4 * firstScale;
  const middleTop = firstBottom + rowGap + depth * recession * small;
  const middleWidth = span(middle.length, small);
  const middleLeft = (width - middleWidth) / 2;
  const ruleTop = middleTop + (4 * small - rule.height) / 2;
  const bar = (side, x, length) => ({ rule: [length / small, rule.height / small], side, x, y: ruleTop, scale: small, row: 1, word: 1, lighter: middle[0].lighter });
  const lastTop = middleTop + 4 * small + rowGap + depth * recession * lastScale;
  const pieces = [
    ...row(first, 0, 0, firstScale, gap * firstScale),
    bar('left', 0, middleLeft - rule.gap),
    ...row(middle, middleLeft, middleTop, small, gap, 1),
    bar('right', middleLeft + middleWidth + rule.gap, width - middleLeft - middleWidth - rule.gap),
    ...row(last, 0, lastTop, lastScale, gap * lastScale, 2),
  ];
  return { pieces, words: split.map(w => w.map(l => l.c).join('')), height: lastTop + 4 * lastScale, rows: [[0, firstBottom], [middleTop, middleTop + 4 * small], [lastTop, lastTop + 4 * lastScale]] };
}

// A piece's place: its offset, and its scale where it has one. Strokes divide by the scale, so
// a scaled piece keeps the edge width of the rest.
export const placement = ({ x, y, scale }) => y === 0 && scale === 1 ? `translate(${round(x)} 0)` : `translate(${round(x)} ${round(y)})${scale === 1 ? '' : ` scale(${Number(scale.toFixed(4))})`}`;

// The rightmost and topmost reach of the pieces, extrusions included.
function reach(pieces) {
  return pieces.reduce(([right, top], { rule, x, y, scale }) => [
    Math.max(right, x + ((rule?.[0] ?? 3) + depth * recession) * scale),
    Math.min(top, y - depth * recession * scale),
  ], [-Infinity, Infinity]);
}

// Lower rows first, then left to right: each piece's extrusion recedes up and to the right,
// behind the pieces above it and to its right.
export const paintOrder = pieces => [...pieces].sort((a, b) => b.row - a.row || a.x - b.x);

function drawPiece(piece, { palette, edgeWidth, cShape }) {
  const { c, rule, scale, lighter } = piece;
  const faces = lighter ? light : palette;
  const place = placement(piece), stroke = round(edgeWidth / scale);
  if (rule) {
    const [w, h] = rule;
    return chamferLetter([[0, 0], [w, 0], [w, h], [0, h], [0, 0]], null, place, faces, stroke);
  }
  const rows = c === 'C' ? cRows(cShape) : glyphs[c];
  const profile = c === 'C' && cShape !== 'bold' ? null : chamferProfiles[c];
  return profile ? chamferLetter(profile, counters[c], place, faces, stroke) : letter(rows, place, 4, faces, stroke);
}

// `lighter` lists letter indices drawn in the lighter blue (TEXTTOCAD's "TO"); `words` and
// `stacked` are logoLayout's. `id` prefixes the relief's gradient, clip and filter ids, so two
// drawings of one word can share a document.
export function logoArtwork(text, { standalone = false, palette = colors, edgeWidth = 0.038, cShape = 'bold', finish = 'soft-relief', lighter = [], words, stacked = false, id = `relief-${text.toLowerCase()}${stacked ? '-stacked' : ''}` } = {}) {
  const layout = logoLayout(text, { words, stacked, lighter });
  const parts = paintOrder(layout.pieces).map(piece => drawPiece(piece, { palette, edgeWidth, cShape }));
  // Include the shadow in exported SVG and raster bounds.
  const margin = finish === 'soft-relief' ? 0.36 : 0.16;
  const [width, top] = reach(layout.pieces);
  const boxHeight = layout.height - top + margin * 2;
  const boxWidth = standalone ? boxHeight : width + margin * 2;
  const left = standalone ? (width - boxWidth) / 2 : -margin;
  const body = parts.join('');
  const name = stacked ? layout.words.join(' ') : text;
  return {
    box: [left, top - margin, boxWidth, boxHeight].map(round),
    label: standalone ? 'text-to-cad C logo' : name,
    title: standalone ? 'text-to-cad' : name,
    artwork: finish === 'soft-relief' ? softRelief(body, id) : body,
  };
}

export function logoSvg(text, options = {}) {
  const { box, label, title, artwork } = logoArtwork(text, options);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${box.join(' ')}" role="img" aria-label="${label}"><title>${title}</title>${artwork}</svg>\n`;
}

// Whether a letter is drawn from its block rows (letter()) rather than its chamfer profile.
export const blockGlyph = c => c in glyphs && !(c in chamferProfiles);

// A letter's closed front loops in its own 3 × 4 box: the outline, then any counter.
export function letterLoops(c) {
  return chamferProfiles[c]
    ? [chamferProfiles[c], ...(counters[c] ? [counters[c]] : [])]
    : outline(glyphs[c], 4 / glyphs[c].length, 3 / glyphs[c][0].length)
      .split('M').filter(Boolean).map(loop => loop.replace(/Z$/, '').split('L').map(p => p.split(',').map(Number)));
}

// CAD consumes these exact front outlines instead of maintaining a second alphabet.
export function logoProfiles() {
  const letters = {};
  for (const c of 'CTEXADO') letters[c] = letterLoops(c);
  return { unitMm: 10, height: 4, width: 3, depth, gap, color: colors.front, lighterColor: light.front, letters };
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  await mkdir(out, { recursive: true });
  for (const [name, text, options] of [
    ['logo-c', 'C', { standalone: true }],
    ['logo-cad', 'CAD', {}],
    ['logo-texttocad', 'TEXTTOCAD', { lighter: [4, 5] }],
    ['logo-texttocad-stacked', 'TEXTTOCAD', { lighter: [4, 5], words: [4, 2, 3], stacked: true }],
  ]) {
    await writeFile(path.join(out, `${name}.svg`), logoSvg(text, options));
  }
  const cadSources = path.join(root, 'models/branding/src');
  await mkdir(cadSources, { recursive: true });
  await writeFile(path.join(cadSources, 'profiles.json'), `${JSON.stringify(logoProfiles(), null, 2)}\n`);
  console.log('Generated C, CAD, TEXTTOCAD and the stacked TEXT TO CAD and the CAD profiles; run export-logos.mjs for the rasters and app copies.');
}
