// @vitest-environment node
// The page's build configuration runs in Node, never in a page.
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { afterEach, expect, it, vi } from 'vitest';
import { version } from '../package.json';

afterEach(() => { vi.unstubAllEnvs(); });

/** The build id this page's Vite config hands it (`__TEXT_TO_CAD_BUILD__`) when the build's environment is `release`'s. */
async function named(release: string | undefined): Promise<string> {
  vi.stubEnv('TEXT_TO_CAD_RELEASE', release);
  // The config reads its environment when it loads, as a build loads it once.
  vi.resetModules();
  const { default: config } = await import('../vite.config.mjs');
  return JSON.parse(config.define.__TEXT_TO_CAD_BUILD__);
}

it('builds the page with no build id for the release\'s own build, and its checkout\'s commit for any other', async () => {
  const commit = execFileSync('git', ['rev-parse', '--short', 'HEAD'], { cwd: fileURLToPath(new URL('..', import.meta.url)), encoding: 'utf8' }).trim();
  expect(await named(version)).toBe('');
  expect(await named(undefined)).toMatch(new RegExp(`^${commit}(?:-dirty)?$`, 'u'));
});
