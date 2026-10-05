// The animated marks end on the static mark: every animation holds its element's own attribute
// value as its last frame, and with no animation running only the static artwork shows. The
// shipped files are the generator's output, and every path morph keeps one command structure,
// which is what lets a browser interpolate it rather than jump.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { animatedLogoSvg, marks } from './animate-logos.mjs';
import { logoArtwork } from './generate-logos.mjs';

// What a renderer uses for an attribute the element does not set.
const initial = { opacity: '1', visibility: 'visible' };

function parse(svg) {
  const root = { children: [] };
  const stack = [root];
  for (const [, close, name, attributes, empty] of svg.matchAll(/<(\/?)([\w:-]+)((?:\s+[\w:-]+="[^"]*")*)\s*(\/?)>/g)) {
    if (close) { stack.pop(); continue; }
    const node = { name, attrs: Object.fromEntries([...attributes.matchAll(/([\w:-]+)="([^"]*)"/g)].map(m => m.slice(1))), children: [] };
    stack.at(-1).children.push(node);
    if (!empty) stack.push(node);
  }
  return root.children[0];
}

const walk = function* (node) {
  yield node;
  for (const child of node.children) yield* walk(child);
};

for (const [name, text, options] of marks) {
  const svg = animatedLogoSvg(text, options);
  const animations = [...walk(parse(svg))].flatMap(node => node.children.filter(c => c.name === 'animate').map(a => [node, a.attrs]));

  test(`${name}-animated.svg is the generator's output`, async () => {
    const shipped = await readFile(new URL(`../../apps/docs/public/brand/${name}-animated.svg`, import.meta.url), 'utf8');
    assert.equal(shipped, svg, 'run node scripts/brand/animate-logos.mjs');
  });

  test(`${name}: without SMIL, only the static artwork shows`, () => {
    const still = svg.replace(/<animate\b[^>]*\/>/g, '');
    const { artwork } = logoArtwork(text, { ...options, id: `build-${text.toLowerCase()}${options.stacked ? '-stacked' : ''}` });
    assert.ok(still.endsWith(`<g>${artwork}</g></svg>\n`));
    const layers = parse(svg).children.filter(c => c.name === 'g').slice(0, -1);
    assert.ok(layers.length > 1);
    for (const layer of layers) assert.ok(layer.attrs.opacity === '0' || layer.attrs.visibility === 'hidden', JSON.stringify(layer.attrs));
  });

  test(`${name}: every animation ends where a still render stands`, () => {
    assert.ok(animations.length > 10);
    for (const [node, a] of animations) {
      const values = a.values.split(';'), times = a.keyTimes.split(';').map(Number);
      assert.equal(times.length, values.length);
      assert.equal(times[0], 0);
      assert.ok(times.every((t, i) => i === 0 || t > times[i - 1]) && times.at(-1) <= 1, a.keyTimes);
      if (a.calcMode === 'spline') assert.equal(a.keySplines.split(';').length, values.length - 1);
      assert.equal(values.at(-1), node.attrs[a.attributeName] ?? initial[a.attributeName], `${node.name} ${a.attributeName}`);
    }
  });

  test(`${name}: path morphs keep one command structure`, () => {
    const morphs = animations.filter(([, a]) => a.attributeName === 'd');
    assert.ok(morphs.length);
    for (const [, a] of morphs) {
      const shapes = new Set(a.values.split(';').map(d => d.replace(/-?[\d.]+/g, 'n')));
      assert.equal(shapes.size, 1, a.values);
    }
  });
}
