// End to end with the real local provider: a tiny generated box is built by
// apps/cloud/runner/run.py with cadgen, then snapshotted and inspected. Each job gets its
// own temporary folder and cadgen store (CADGEN_CACHE_DIR inside the job, CADGEN_DAEMON=0).
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createLocalSandbox } from '../server/sandbox/local.ts';
import { boxSource, testServer, type TestServer } from './helpers.ts';

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const python = process.env.CLOUD_PYTHON || path.resolve(APP, '../../.venv/bin/python');
const usable = existsSync(python) &&
  spawnSync(python, ['-c', 'import importlib.util as u, sys; sys.exit(0 if u.find_spec("cadgen") and u.find_spec("build123d") else 1)']).status === 0;
const skipReason = `skipped: no cadgen-capable Python at ${python} (set CLOUD_PYTHON)`;
if (!usable) process.stderr.write(`[e2e] ${skipReason}\n`);

describe.skipIf(!usable)(`local sandbox, end to end${usable ? '' : ` (${skipReason})`}`, () => {
  let server: TestServer;
  beforeAll(async () => {
    server = await testServer({
      env: { CLOUD_TOOL_WAIT_S: '120' },
      sandbox: createLocalSandbox({ python, runner: path.join(APP, 'runner/run.py') }),
    });
  });
  afterAll(async () => {
    await server?.close();
  });

  it('builds a box, then snapshots and inspects it', async () => {
    const build = await (await server.request('/v1/builds?wait=120', {
      method: 'POST',
      json: { files: { 'src/box.py': boxSource('box', 20) }, entry: 'src/box.py' },
    })).json();
    expect(build, JSON.stringify(build.error)).toMatchObject({ status: 'succeeded', primary: 'STEP/box.step', outputs: ['STEP/box.step'] });
    expect(build.thumbnail).toMatch(/\/o\/o\/[0-9a-f]{64}$/);
    expect(build.cadgen).toMatch(/^\d+\.\d+/);

    const snapshot = await (await server.request(`/v1/builds/${build.id}/snapshot?wait=120`, { method: 'POST', json: { args: ['--width', '320', '--height', '240'] } })).json();
    expect(snapshot, JSON.stringify(snapshot.error)).toMatchObject({ status: 'succeeded', images: [{ type: 'image/png' }] });

    const inspect = await (await server.request(`/v1/builds/${build.id}/inspect?wait=120`, {
      method: 'POST',
      json: { code: 'from cadgen import read_step\nshape = read_step("STEP/box.step")\nprint("volume", round(shape.volume))\n' },
    })).json();
    expect(inspect, inspect.stderr).toMatchObject({ status: 'succeeded', exitCode: 0 });
    expect(inspect.stdout).toContain('volume 1000');
  }, 180_000);
});
