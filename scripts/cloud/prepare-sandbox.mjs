#!/usr/bin/env node
// Make the Vercel Sandbox snapshot every cloud job starts from, and print its id:
//
//   node scripts/cloud/prepare-sandbox.mjs        # then set CLOUD_SANDBOX_SNAPSHOT=<id>
//
// The snapshot holds Python 3.13 with cadgen==VERSION (the release on PyPI), the headless
// browser cadgen's snapshots drive, Node from the image (mesh export), and
// apps/cloud/runner at /vercel/sandbox/runner. Setup has the network; then the network is
// cut and a smoke job builds and snapshots a box the way a real job does, so a snapshot
// that would need a download at run time is never saved.
//
// It creates cloud resources: run it by hand, never in CI. Credentials come from
// VERCEL_OIDC_TOKEN (`vercel env pull`) or VERCEL_TEAM_ID + VERCEL_PROJECT_ID + VERCEL_TOKEN.
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Sandbox } from '@vercel/sandbox';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const ROOT = '/vercel/sandbox';
const VERSION = (await readFile(path.join(REPO, 'VERSION'), 'utf8')).trim();
const PYTHON = `${ROOT}/venv/bin/python`;

const credentials = process.env.VERCEL_TEAM_ID && process.env.VERCEL_PROJECT_ID && process.env.VERCEL_TOKEN
  ? { teamId: process.env.VERCEL_TEAM_ID, projectId: process.env.VERCEL_PROJECT_ID, token: process.env.VERCEL_TOKEN }
  : {};

const log = (message) => process.stderr.write(`prepare-sandbox: ${message}\n`);

async function run(sandbox, script, { sudo = false } = {}) {
  const result = await sandbox.runCommand({ cmd: 'bash', args: ['-lc', `set -euo pipefail\n${script}`], sudo, stdout: process.stderr, stderr: process.stderr });
  if (result.exitCode !== 0) throw new Error(`exited ${result.exitCode}:\n${script}`);
}

const BOX = `from cadgen import build123d as bd
from cadgen import step


@step(out="../STEP/box.step")
def box():
    body = bd.Box(20, 10, 5)
    body.label = "box"
    return body


if __name__ == "__main__":
    box()
`;

log(`creating a sandbox for cadgen==${VERSION}`);
const sandbox = await Sandbox.create({ resources: { vcpus: 2 }, timeout: 45 * 60_000, networkPolicy: 'allow-all', ...credentials });
let saved = false;
try {
  log('installing uv, Python 3.13 and cadgen');
  await run(sandbox, `export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.13 ${ROOT}/venv
uv pip install --python ${PYTHON} --compile-bytecode "cadgen==${VERSION}"
node --version`);
  log("installing the snapshot browser and its system libraries");
  await run(sandbox, `${PYTHON} -m playwright install --only-shell chromium`);
  await run(sandbox, `${PYTHON} -m playwright install-deps chromium`, { sudo: true });

  log('copying the runner');
  await sandbox.writeFiles([
    { path: `${ROOT}/runner/run.py`, content: await readFile(path.join(REPO, 'apps/cloud/runner/run.py')) },
    { path: `${ROOT}/runner/site/sitecustomize.py`, content: await readFile(path.join(REPO, 'apps/cloud/runner/site/sitecustomize.py')) },
    { path: `${ROOT}/smoke/request.json`, content: Buffer.from(JSON.stringify({ kind: 'build', entry: ['src/box.py'], timeoutSeconds: 600, vcpus: 2 })) },
    { path: `${ROOT}/smoke/workspace/src/box.py`, content: Buffer.from(BOX) },
  ]);

  log('cutting the network and running a smoke build');
  await sandbox.update({ networkPolicy: 'deny-all' });
  await run(sandbox, `cd ${ROOT}/smoke/workspace && ${PYTHON} ${ROOT}/runner/run.py ${ROOT}/smoke > /dev/null`);
  const result = JSON.parse((await sandbox.readFileToBuffer({ path: `${ROOT}/smoke/result.json` }))?.toString() ?? '{}');
  if (!result.ok || !result.thumbnail || result.flags?.network) {
    throw new Error(`the smoke build failed: ${JSON.stringify({ ok: result.ok, error: result.error, thumbnail: result.thumbnail, log: result.log })}`);
  }
  if (result.exportError) log(`note: ${result.exportError} (this cadgen records no viewer export)`);
  await run(sandbox, `rm -rf ${ROOT}/smoke`);

  log('saving the snapshot (this stops the sandbox)');
  const snapshot = await sandbox.snapshot({ expiration: 0 });
  saved = true;
  log(`done: CLOUD_SANDBOX_SNAPSHOT=${snapshot.snapshotId}`);
  process.stdout.write(`${snapshot.snapshotId}\n`);
} finally {
  if (!saved) await sandbox.stop().catch(() => {});
}
