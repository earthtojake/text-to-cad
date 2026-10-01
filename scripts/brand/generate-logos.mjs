// Deterministic vector branding. Run from any directory with Node; no renderer required.
import { mkdir, writeFile, copyFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const out = path.join(root, 'apps/docs/public/brand');
const depth = 2;
const recession = 0.42; // Upright front and receding 45° edges, following the supplied sketch.
const colors = { front: '#249ddd', top: '#62b7ec', side: '#1475ad', edge: '#123e59' };
// Most glyphs use half-unit coordinates. T centers a 1.5-unit stem.
// All letters stay three units wide and four tall.
const glyphs = {
  C: ['111111', '111111', '111111', '111000', '111000', '111111', '111111', '111111'],
  T: ['111111111111', '111111111111', '111111111111', '000111111000', '000111111000', '000111111000', '000111111000', '000111111000'],
  E: ['111111', '111111', '111000', '111111', '111111', '111000', '111111', '111111'],
};
// Straight 45-degree cuts on X, 2, A's top and D's right.
// Counters remain square; no glyph contains curved profile segments.
const chamferProfiles = {
  // Preserve the two-unit waist and square ends; only trim step corners.
  X: [[0,0],[1,0],[1,1],[1.25,1.25],[1.75,1.25],[2,1],[2,0],[3,0],[3,1.5],[2.5,2],[3,2.5],[3,4],[2,4],[2,3],[1.75,2.75],[1.25,2.75],[1,3],[1,4],[0,4],[0,2.5],[0.5,2],[0,1.5],[0,0]],
  2: [[0,0],[2.5,0],[3,0.5],[3,2.5],[1.5,2.5],[1.5,3],[3,3],[3,4],[0,4],[0,1.5],[1.5,1.5],[1.5,1],[0,1],[0,0]],
  A: [[0,0.5],[0.5,0],[2.5,0],[3,0.5],[3,4],[2,4],[2,3.5],[1,3.5],[1,4],[0,4],[0,0.5]],
  D: [[0,0],[2.5,0],[3,0.5],[3,3.5],[2.5,4],[0,4],[0,0]],
};
const counters = {
  A: [[1,1],[1,2],[2,2],[2,1],[1,1]],
  D: [[1,1],[1,3],[2,3],[2,1],[1,1]],
};
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

function letter(rows, x, height, palette, edgeWidth) {
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
  return `<g transform="translate(${round(x)} 0)">${faces.join('')}<path${edge} fill="${palette.front}" fill-rule="evenodd" d="${outline(rows, rowHeight, columnWidth)}"/></g>`;
}

function chamferLetter(vertices, counter, x, palette, edgeWidth) {
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
  return `<g transform="translate(${round(x)} 0)">${faces.map(f => f.svg).join('')}<path${edge} fill="${palette.front}" fill-rule="evenodd" d="${loops.map(outline).join('')}"/></g>`;
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
function softRelief(body, id) {
  const defs = [
    `<linearGradient id="${id}-front" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="2" y2="4"><stop stop-color="#39b0e9"/><stop offset=".5" stop-color="#249ddd"/><stop offset="1" stop-color="#1785bf"/></linearGradient>`,
    `<linearGradient id="${id}-top" gradientUnits="userSpaceOnUse" x1="0" y1="-1" x2="3" y2="4"><stop stop-color="#94d9fa"/><stop offset="1" stop-color="#51ade1"/></linearGradient>`,
    `<linearGradient id="${id}-side" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="4" y2="3"><stop stop-color="#258cc5"/><stop offset="1" stop-color="#0b5887"/></linearGradient>`,
    `<filter id="${id}-shadow" x="-30%" y="-40%" width="170%" height="200%" color-interpolation-filters="sRGB"><feDropShadow dx=".035" dy=".10" stdDeviation=".075" flood-color="#082f4a" flood-opacity=".22"/></filter>`,
  ];
  let index = 0;
  const shaded = body.replace(/<path([^>]*?)\/>/g, (original, attrs) => {
    const fill = attrs.match(/fill="([^"]+)"/)?.[1];
    const face = { [colors.front]: 'front', [colors.top]: 'top', [colors.side]: 'side' }[fill];
    if (!face) return original;
    let result = `<path${attrs.replace(`fill="${fill}"`, `fill="url(#${id}-${face})"`)}/>`;
    if (face !== 'side') {
      const d = attrs.match(/ d="([^"]+)"/)[1];
      const clip = `${id}-highlight-${index++}`;
      defs.push(`<clipPath id="${clip}"><path d="${d}" clip-rule="evenodd"/></clipPath>`);
      result += `<g clip-path="url(#${clip})"><path d="${d}" fill="none" stroke="#d1f1ff" stroke-opacity="${face === 'top' ? '.6' : '.38'}" stroke-width=".037" transform="translate(.042 .042)"/></g>`;
    }
    return result;
  });
  return `<defs>${defs.join('')}</defs><g filter="url(#${id}-shadow)">${shaded}</g>`;
}

export function logoSvg(text, { standalone = false, palette = colors, edgeWidth = 0.038, cShape = 'bold', finish = 'soft-relief' } = {}) {
  const height = 4;
  let x = 0;
  const parts = [];
  for (const c of text) {
    const rows = c === 'C' ? cRows(cShape) : glyphs[c];
    const profile = c === 'C' && cShape !== 'bold' ? null : chamferProfiles[c];
    parts.push(profile ? chamferLetter(profile, counters[c], x, palette, edgeWidth) : letter(rows, x, height, palette, edgeWidth));
    x += 3 + 1.25;
  }
  // Include the shadow in exported SVG and raster bounds.
  const margin = finish === 'soft-relief' ? 0.36 : 0.16;
  const width = x - 1.25 + depth * recession;
  const boxHeight = height + depth * recession + margin * 2;
  const boxWidth = standalone ? boxHeight : width + margin * 2;
  const left = standalone ? (width - boxWidth) / 2 : -margin;
  const body = parts.join('');
  const artwork = finish === 'soft-relief' ? softRelief(body, `relief-${text.toLowerCase()}`) : body;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${round(left)} ${round(-depth*recession-margin)} ${round(boxWidth)} ${round(boxHeight)}" role="img" aria-label="${standalone ? 'text-to-cad C logo' : text}"><title>${standalone ? 'text-to-cad' : text}</title>${artwork}</svg>\n`;
}

// CAD consumes these exact front outlines instead of maintaining a second alphabet.
export function logoProfiles() {
  const letters = {};
  for (const c of 'CTEX2AD') {
    const loops = chamferProfiles[c]
      ? [chamferProfiles[c], ...(counters[c] ? [counters[c]] : [])]
      : outline(glyphs[c], 4 / glyphs[c].length, 3 / glyphs[c][0].length)
        .split('M').filter(Boolean).map(loop => loop.replace(/Z$/, '').split('L').map(p => p.split(',').map(Number)));
    letters[c] = loops;
  }
  return { unitMm: 10, height: 4, width: 3, depth, gap: 1.25, color: colors.front, letters };
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  await mkdir(out, { recursive: true });
  for (const [name, text, standalone] of [['logo-c', 'C', true], ['logo-cad', 'CAD', false], ['logo-text2cad', 'TEXT2CAD', false]]) {
    await writeFile(path.join(out, `${name}.svg`), logoSvg(text, { standalone }));
  }
  // The viewer's home and version menu draw the CAD wordmark from the shared UI package.
  await copyFile(path.join(out, 'logo-cad.svg'), path.join(root, 'packages/ui/src/assets/logo-cad.svg'));
  const cadSources = path.join(root, 'models/branding/src');
  await mkdir(cadSources, { recursive: true });
  await writeFile(path.join(cadSources, 'profiles.json'), `${JSON.stringify(logoProfiles(), null, 2)}\n`);
  console.log('Generated C, CAD and TEXT2CAD; synchronized the viewer marks and CAD profiles.');
}
