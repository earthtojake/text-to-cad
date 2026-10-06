// Test dependencies: PGlite in memory, an fs store in a temporary folder, a scripted
// sandbox, and the real app on top. Nothing here touches the network or models/.
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { buildApp } from '../server/app.ts';
import { createAuth, type AuthOptions } from '../server/auth.ts';
import type { Clock } from '../server/clock.ts';
import { loadConfig, type Env } from '../server/config.ts';
import { createPgliteDb, migrate, type Db } from '../server/db/index.ts';
import { sha256Hex } from '../server/ids.ts';
import {
  checkCollected,
  filesToCollect,
  parseRunnerResult,
  type RunnerEvent,
  type RunnerResult,
  type SandboxJob,
  type SandboxProvider,
} from '../server/sandbox/protocol.ts';
import type { Deps } from '../server/service.ts';
import { createFsStore } from '../server/store.ts';

export const PUBLIC_URL = 'http://cloud.test';

export const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3, 4]);

export interface FakeOutcome {
  result?: Partial<RunnerResult>;
  /** Files by path relative to the job dir (workspace/…, out/…). */
  files?: Record<string, Uint8Array | string>;
  events?: RunnerEvent[];
  wallMs?: number;
  /** Raw result.json text, to test what the server does with a malformed one. */
  rawResult?: string;
  /** Listed in result.files with these (lying) sizes or digests instead of the real ones. */
  lies?: Record<string, { bytes?: number; sha256?: string }>;
}

export type FakeHandler = (job: SandboxJob) => FakeOutcome | Promise<FakeOutcome>;

/** A sandbox that answers from a script, through the same result checks as a real one. */
export function fakeSandbox(handler: FakeHandler): SandboxProvider & { jobs: SandboxJob[] } {
  const jobs: SandboxJob[] = [];
  return {
    kind: 'fake',
    jobs,
    async run(job, { onEvent } = {}) {
      jobs.push(job);
      const outcome = await handler(job);
      for (const event of outcome.events ?? []) onEvent?.(event);
      const bytes = new Map<string, Uint8Array>();
      for (const [name, value] of Object.entries(outcome.files ?? {})) bytes.set(name, typeof value === 'string' ? new TextEncoder().encode(value) : value);
      const listed = [...bytes].map(([name, value]) => ({
        path: name,
        bytes: outcome.lies?.[name]?.bytes ?? value.byteLength,
        sha256: outcome.lies?.[name]?.sha256 ?? sha256Hex(value),
      }));
      const result = {
        ok: true, kind: job.kind, exitCode: 0, wallMs: 10, error: null, log: '', stdout: '', stderr: '',
        outputs: [], dropped: [], primary: null, export: null, exportError: null, thumbnail: null, images: [],
        flags: { network: false }, cadgen: '0.0.0-test', files: listed,
        ...outcome.result,
      };
      const parsed = parseRunnerResult(outcome.rawResult ?? JSON.stringify(result));
      const files = new Map<string, Uint8Array>();
      for (const file of filesToCollect(parsed, job.limits)) {
        const value = bytes.get(file.path);
        files.set(file.path, checkCollected(file, value ?? new Uint8Array()));
      }
      return { result: parsed, files, usage: { wallMs: outcome.wallMs ?? 1000 } };
    },
  };
}

/** A successful build of one STEP output with a thumbnail and a one-object export. */
export function successfulBuild(job: SandboxJob, { step = 'ISO-10303-21;\nEND-ISO-10303-21;\n' } = {}): FakeOutcome {
  const entry = String((job.request.entry as string[])[0]);
  const stem = entry.split('/').pop()!.replace(/\.py$/, '');
  const output = `STEP/${stem}.step`;
  const object = new TextEncoder().encode(`surf:${stem}`);
  const sha = sha256Hex(object);
  const exportJson = JSON.stringify({
    schema: 1,
    cadgen: '0.0.0-test',
    files: [{ path: `/${output}`, kind: 'step', bytes: step.length, sha256: sha256Hex(step) }],
    views: [`/${output}`],
    routes: { '/__cad/server': { '': { ok: true } }, '/__cad/asset': { [`/${output}`]: { object: sha, type: 'application/octet-stream', bytes: object.byteLength } } },
  });
  return {
    result: { outputs: [output], primary: output, export: 'out/export', thumbnail: 'out/thumbnail.png', log: `$ python ${entry}\nbuilt ${output}\n` },
    files: {
      [`workspace/${output}`]: step,
      'out/export/export.json': exportJson,
      [`out/export/objects/${sha}`]: object,
      'out/thumbnail.png': PNG,
    },
    events: [{ type: 'progress', entry, state: 'building', phase: 'Building geometry' }],
  };
}

export function testClock(start = Date.UTC(2026, 9, 6, 12, 0, 0)): Clock & { advance(ms: number): void } {
  let now = start;
  return {
    now: () => now,
    advance(ms: number) {
      now += ms;
    },
  };
}

export interface TestServer {
  deps: Deps;
  app: ReturnType<typeof buildApp>['app'];
  service: ReturnType<typeof buildApp>['service'];
  db: Db;
  dir: string;
  request(pathname: string, init?: RequestInit & { json?: unknown }): Promise<Response>;
  close(): Promise<void>;
}

export interface TestServerOptions {
  env?: Env;
  sandbox?: SandboxProvider;
  clock?: Clock;
  auth?: Partial<Pick<AuthOptions, 'jwks' | 'fetch'>>;
  db?: Db;
}

export async function testServer(options: TestServerOptions = {}): Promise<TestServer> {
  const dir = await mkdtemp(path.join(tmpdir(), 't2c-cloud-test-'));
  const config = loadConfig({
    CLOUD_AUTH: 'dev',
    CLOUD_PUBLIC_URL: PUBLIC_URL,
    CLOUD_FS_DIR: path.join(dir, 'store'),
    CLOUD_DIST_DIR: path.join(dir, 'dist'),
    CLOUD_SANDBOX: 'local',
    CLOUD_PYTHON: '/nonexistent/python',
    CLOUD_TOOL_WAIT_S: '5',
    ...options.env,
  });
  const db = options.db ?? (await createPgliteDb());
  await migrate(db);
  const clock = options.clock ?? testClock();
  const deps: Deps = {
    config,
    db,
    store: createFsStore(config.storage.kind === 'fs' ? config.storage.dir : path.join(dir, 'store')),
    sandbox: options.sandbox ?? fakeSandbox(successfulBuild),
    auth: createAuth({ config, db, clock, ...options.auth }),
    clock,
    log: () => {},
  };
  const { app, service } = buildApp(deps);
  return {
    deps,
    app,
    service,
    db,
    dir,
    request(pathname, init = {}) {
      const { json, ...rest } = init;
      const headers = new Headers(rest.headers);
      if (json !== undefined) headers.set('content-type', 'application/json');
      return Promise.resolve(app.fetch(new Request(`${PUBLIC_URL}${pathname}`, { ...rest, headers, body: json !== undefined ? JSON.stringify(json) : rest.body })));
    },
    async close() {
      await service.idle();
      if (!options.db) await db.close();
      await rm(dir, { recursive: true, force: true });
    },
  };
}

export const boxSource = (name = 'box', size = 20) => `from cadgen import build123d as bd
from cadgen import step


@step(out="../STEP/${name}.step")
def ${name}():
    body = bd.Box(${size}, 10, 5)
    body.label = "${name}"
    return body


if __name__ == "__main__":
    ${name}()
`;

/** A promise you resolve later: holds a fake sandbox job "running" until the test says so. */
export function gate() {
  let open!: () => void;
  const promise = new Promise<void>((resolve) => {
    open = resolve;
  });
  return { promise, open };
}
