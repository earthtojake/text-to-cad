import { spawn, type StdioOptions } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  parseChannelPointer,
  protocolMajor,
  type ReleaseChannel,
} from '@emdash/core/workspace-server';
import { createDevPackageVersion } from './package-helpers.ts';
import { channelPointerUrl } from './upload-helpers.ts';

const linuxTargets = ['linux-arm64', 'linux-x64'] as const;
type LinuxTarget = (typeof linuxTargets)[number];

const appDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repositoryDirectory = resolve(appDirectory, '../..');
const minioBucket = process.env['EMDASH_WS_DEV_MINIO_BUCKET'] ?? 'emdash-releases';
const minioHostEndpoint =
  process.env['EMDASH_WS_DEV_MINIO_ENDPOINT'] ?? `http://localhost:9000/${minioBucket}`;
const minioArtifactsUrl =
  process.env['EMDASH_WS_DEV_ARTIFACTS_URL'] ?? `http://minio:9000/${minioBucket}/workspace-server`;

async function main(): Promise<void> {
  const target = resolveTarget(process.env['EMDASH_WS_DEV_REMOTE_TARGET']);
  const expectedVersion = await resolveDevVersion();
  process.stdout.write(`Packaging workspace-server ${expectedVersion} for ${target}...\n`);
  await runCommand('pnpm', ['run', 'package', '--target', target], {
    env: {
      ...process.env,
      EMDASH_WS_DEV_BUILD: '1',
      EMDASH_WS_DEV_VERSION: expectedVersion,
    },
  });

  process.stdout.write('Starting docker remote infrastructure...\n');
  await runCommand('docker', ['compose', 'up', '--build', '-d', 'minio']);
  await runCommand('docker', ['compose', 'up', 'minio-setup']);
  await runCommand('docker', ['compose', 'up', '--build', '-d', 'workspace-remote'], {
    env: {
      ...process.env,
      ...(target === 'linux-x64' && process.arch === 'arm64'
        ? { WORKSPACE_REMOTE_PLATFORM: 'linux/amd64' }
        : {}),
    },
  });

  await waitForMinio();

  process.stdout.write(`Uploading workspace-server ${expectedVersion} to local minio...\n`);
  await runCommand(
    'tsx',
    [
      'scripts/upload-r2.ts',
      '--version',
      expectedVersion,
      '--target',
      target,
      '--channel',
      'stable',
      '--channel',
      'canary',
    ],
    {
      cwd: appDirectory,
      env: {
        ...process.env,
        EMDASH_WS_UPLOAD_ENDPOINT: minioHostEndpoint,
        EMDASH_WS_UPLOAD_ACCESS_KEY: process.env['EMDASH_WS_UPLOAD_ACCESS_KEY'] ?? 'minioadmin',
        EMDASH_WS_UPLOAD_SECRET_KEY: process.env['EMDASH_WS_UPLOAD_SECRET_KEY'] ?? 'minioadmin',
      },
    }
  );

  await verifyPublishedVersion(expectedVersion);

  process.stdout.write(`
Docker remote is ready on localhost:2223 (devuser / devpass).
Workspace-server ${expectedVersion} is published to ${minioArtifactsUrl}.

Launch the desktop app with:
pnpm run dev:remote-app

or equivalently:
EMDASH_WORKSPACE_SERVER_ARTIFACTS_URL=${minioArtifactsUrl} EMDASH_WORKSPACE_SERVER_DEV_AUTO_UPDATE=1 pnpm --dir ../emdash-desktop run dev
`);
}

async function resolveDevVersion(): Promise<string> {
  const packageVersion = await readPackageVersion();
  const explicitDevVersion = process.env['EMDASH_WS_DEV_VERSION']?.trim();
  if (explicitDevVersion !== undefined && explicitDevVersion.length > 0) {
    return createDevPackageVersion(packageVersion, explicitDevVersion);
  }
  return createDevPackageVersion(packageVersion, await devBuildIdentifier());
}

async function readPackageVersion(): Promise<string> {
  const raw: unknown = JSON.parse(await readFile(join(appDirectory, 'package.json'), 'utf8'));
  if (!isRecord(raw) || typeof raw['version'] !== 'string') {
    throw new Error('workspace-server package.json must contain a string version');
  }
  return raw['version'];
}

async function devBuildIdentifier(): Promise<string> {
  const timestamp = String(Math.floor(Date.now() / 1000));
  try {
    const sha = (
      await runCommandOutput('git', ['rev-parse', '--short', 'HEAD'], {
        cwd: repositoryDirectory,
      })
    ).trim();
    if (/^[0-9A-Za-z]+$/.test(sha)) return `${sha}.${timestamp}`;
  } catch {
    // Fall back below when this source tree is not a git checkout.
  }
  return timestamp;
}

async function verifyPublishedVersion(expectedVersion: string): Promise<void> {
  const channels = ['stable', 'canary'] as const satisfies readonly ReleaseChannel[];
  const major = protocolMajor();
  process.stdout.write(`Verifying the published minio protocol-${major} channel pointers...\n`);
  const deadline = Date.now() + 30_000;
  let lastError = 'channel pointers were never checked';

  while (Date.now() < deadline) {
    try {
      let allPointersMatch = true;
      for (const channel of channels) {
        const pointerUrl = channelPointerUrl(minioHostEndpoint, channel, major);
        const response = await fetch(pointerUrl);
        if (!response.ok) {
          lastError = `${channel} pointer returned HTTP ${response.status}`;
          allPointersMatch = false;
          break;
        }

        const pointer = parseChannelPointer(await response.text(), major);
        if (!pointer.success) {
          lastError = `${channel} pointer is invalid: ${JSON.stringify(pointer.error)}`;
          allPointersMatch = false;
          break;
        }
        if (pointer.data.artifactVersion !== expectedVersion) {
          lastError = `${channel} pointer reports ${pointer.data.artifactVersion}, expected ${expectedVersion}`;
          allPointersMatch = false;
          break;
        }
      }

      if (allPointersMatch) {
        process.stdout.write(`Published stable and canary pointers point at ${expectedVersion}\n`);
        return;
      }
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await delay(1_000);
  }

  throw new Error(`Minio did not publish ${expectedVersion}: ${lastError}`);
}

async function waitForMinio(): Promise<void> {
  const deadline = Date.now() + 30_000;
  const endpoint = minioHostEndpoint.replace(/\/$/, '');
  let lastError = 'minio was never checked';

  while (Date.now() < deadline) {
    try {
      const response = await fetch(endpoint);
      if (response.status < 500) return;
      lastError = `minio returned HTTP ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await delay(1_000);
  }

  throw new Error(`Minio did not become reachable: ${lastError}`);
}

async function delay(ms: number): Promise<void> {
  await new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
}

function resolveTarget(value: string | undefined): LinuxTarget {
  if (value === undefined || value.trim().length === 0) {
    return process.arch === 'arm64' ? 'linux-arm64' : 'linux-x64';
  }
  if (isLinuxTarget(value)) return value;
  throw new Error(`Unsupported dev remote target '${value}'. Expected ${linuxTargets.join(', ')}`);
}

function isLinuxTarget(value: string): value is LinuxTarget {
  return (linuxTargets as readonly string[]).includes(value);
}

async function runCommand(
  command: string,
  args: string[],
  options: {
    env?: NodeJS.ProcessEnv;
    cwd?: string;
    stdio?: StdioOptions;
  } = {}
): Promise<void> {
  await new Promise<void>((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      stdio: options.stdio ?? 'inherit',
    });
    child.once('error', rejectPromise);
    child.once('exit', (code, signal) => {
      if (code === 0) {
        resolvePromise();
        return;
      }
      rejectPromise(
        new Error(
          `${command} exited ${signal === null ? `with code ${String(code)}` : `on signal ${signal}`}`
        )
      );
    });
  });
}

async function runCommandOutput(
  command: string,
  args: string[],
  options: {
    cwd?: string;
  } = {}
): Promise<string> {
  return await new Promise<string>((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, { cwd: options.cwd, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (chunk: string) => {
      stdout += chunk;
    });
    child.stderr.on('data', (chunk: string) => {
      stderr += chunk;
    });
    child.once('error', rejectPromise);
    child.once('exit', (code, signal) => {
      if (code === 0) {
        resolvePromise(stdout);
        return;
      }
      const output = stderr.trim();
      rejectPromise(
        new Error(
          `${command} exited ${signal === null ? `with code ${String(code)}` : `on signal ${signal}`}${
            output ? `: ${output}` : ''
          }`
        )
      );
    });
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

void main().catch((error: unknown) => {
  process.stderr.write(
    `workspace-server dev remote failed: ${error instanceof Error ? error.message : String(error)}\n`
  );
  process.exit(1);
});
