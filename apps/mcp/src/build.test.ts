// @vitest-environment node
// The page's build configuration runs in Node, never in a page.
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { inflateSync } from 'node:zlib';
import { afterEach, expect, it, vi } from 'vitest';
import { version } from '../package.json';

afterEach(() => { vi.unstubAllEnvs(); });

/** The build id this page's Vite config hands it (`__CAD_BUILD__`) when the build's environment is `release`'s. */
async function named(release: string | undefined): Promise<string> {
  vi.stubEnv('CAD_RELEASE', release);
  // The config reads its environment when it loads, as a build loads it once.
  vi.resetModules();
  const { default: config } = await import('../vite.config.mjs');
  return JSON.parse(config.define.__CAD_BUILD__);
}

it('builds the page with no build id for the release\'s own build, and its checkout\'s commit for any other', async () => {
  const commit = execFileSync('git', ['rev-parse', '--short', 'HEAD'], { cwd: fileURLToPath(new URL('..', import.meta.url)), encoding: 'utf8' }).trim();
  expect(await named(version)).toBe('');
  expect(await named(undefined)).toMatch(new RegExp(`^${commit}(?:-dirty)?$`, 'u'));
});

/** The RGBA pixel at (x, y) of an 8-bit RGBA PNG (`shell.html`'s icon), its rows unfiltered as PNG says. */
function pixel(png: Buffer, x: number, y: number): number[] {
  let at = 8, width = 0, height = 0;
  const data: Buffer[] = [];
  while (at < png.length) {
    const length = png.readUInt32BE(at), type = png.toString('latin1', at + 4, at + 8), body = png.subarray(at + 8, at + 8 + length);
    if (type === 'IHDR') { width = body.readUInt32BE(0); height = body.readUInt32BE(4); expect([body[8], body[9]]).toEqual([8, 6]); }
    if (type === 'IDAT') data.push(body);
    at += 12 + length;
  }
  const raw = inflateSync(Buffer.concat(data)), stride = width * 4, rows: Buffer[] = [];
  for (let row = 0; row < height; row++) {
    const filter = raw[row * (stride + 1)], line = Buffer.from(raw.subarray(row * (stride + 1) + 1, (row + 1) * (stride + 1)));
    const up = rows[row - 1] ?? Buffer.alloc(stride);
    for (let i = 0; i < stride; i++) {
      const a = i >= 4 ? line[i - 4] : 0, b = up[i], c = i >= 4 ? up[i - 4] : 0, p = a + b - c;
      const paeth = Math.abs(p - a) <= Math.abs(p - b) && Math.abs(p - a) <= Math.abs(p - c) ? a : Math.abs(p - b) <= Math.abs(p - c) ? b : c;
      line[i] = (line[i] + [0, a, b, (a + b) >> 1, paeth][filter]) & 255;
    }
    rows.push(line);
  }
  return [...rows[y].subarray(x * 4, x * 4 + 4)];
}

it('names a host\'s tab CAD and gives it the blue brand mark, as the page\'s own title and icon', () => {
  // Codex titles a CAD tab with the page's <title> and draws its icon from the page's icon, which it takes only as a
  // PNG, JPEG, WebP or GIF data URL of at most 8192 characters: an SVG, or currentColor, would draw nothing or black.
  const shell = readFileSync(fileURLToPath(new URL('../shell.html', import.meta.url)), 'utf8');
  expect(shell.match(/<title>([^<]*)<\/title>/u)?.[1]).toBe('CAD');
  const icon = shell.match(/<link rel="icon" type="image\/png" href="(data:image\/png;base64,[A-Za-z0-9+/]+=*)"/u)?.[1];
  expect(icon?.length).toBeLessThanOrEqual(8192);
  // The mark's front face, left of its notch: the brand blue (#249ddd), opaque.
  const [red, green, blue, alpha] = pixel(Buffer.from(icon!.split(',')[1], 'base64'), 8, 16);
  expect(alpha).toBe(255);
  expect(blue - red).toBeGreaterThan(120);
  expect(blue - green).toBeGreaterThan(40);
});
