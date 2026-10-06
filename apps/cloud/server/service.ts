// The one service layer under REST and MCP: builds, snapshot and inspection jobs, their
// caps, the sandbox round trip, and everything stored from it.
//
// Build flow: validate -> store input files as objects -> reserve compute -> row (queued)
// -> sandbox (running) -> store outputs, export objects, export.json, thumbnail -> row
// (succeeded | failed) -> settle what it really cost. Builds are immutable: an edit is a
// new build from a base build's files plus the changes.
import type { Auth, User } from './auth.ts';
import type { Clock } from './clock.ts';
import { iso } from './clock.ts';
import type { Config } from './config.ts';
import type { Db, Row } from './db/index.ts';
import { isUniqueViolation } from './db/index.ts';
import { CloudError, badRequest, forbidden, notFound } from './errors.ts';
import type { ExportIndex } from './exportIndex.ts';
import { isBuildId, newId, sha256Hex } from './ids.ts';
import type { Reservation, Usage } from './limits.ts';
import { reserve, settle, usageOf } from './limits.ts';
import { contentTypeFor, imageType, isPng } from './mime.ts';
import { stripModelScripts } from './sanitize.ts';
import type { RunnerEvent, RunnerResult, SandboxProvider, SandboxRun } from './sandbox/protocol.ts';
import { SandboxError } from './sandbox/protocol.ts';
import type { ObjectStore } from './store.ts';
import { objectKey, putObject } from './store.ts';
import type { FileRef } from './validate.ts';
import {
  isViewable,
  normalizePath,
  parseBuildRef,
  validateBuild,
  validateCode,
  validateFormat,
  validateSnapshotArgs,
} from './validate.ts';

export interface Deps {
  config: Config;
  db: Db;
  store: ObjectStore;
  sandbox: SandboxProvider;
  auth: Auth;
  clock: Clock;
  /** Keeps work alive after a response (Vercel's waitUntil); defaults to fire-and-forget. */
  background?: (task: Promise<unknown>) => void;
  log?: (message: string, extra?: Record<string, unknown>) => void;
}

export type Status = 'queued' | 'running' | 'succeeded' | 'failed';

export interface JobError {
  message: string;
  file?: string | null;
  line?: number | null;
  kind: 'model' | 'timeout' | 'limit' | 'runner' | 'infra';
}

export interface Progress {
  state?: string;
  phase?: string | null;
  entry?: string;
  model?: string | null;
  progress?: [number, number] | null;
  elapsed?: number | null;
  log?: string[];
  at: string;
}

export interface Build {
  id: string;
  userId: string;
  parentId: string | null;
  title: string | null;
  entry: string[];
  pythonpath: string[];
  files: FileRef[];
  status: Status;
  error: JobError | null;
  outputs: FileRef[];
  primary: string | null;
  exportKey: string | null;
  exportError: string | null;
  thumbnailKey: string | null;
  log: string;
  progress: Progress | null;
  cadgen: string | null;
  limits: { timeoutSeconds: number; vcpus: number };
  timings: Record<string, number> | null;
  cost: { vcpuSeconds: number; usd: number } | null;
  flags: { network?: boolean; dropped?: string[] } | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface JobImage {
  key: string;
  url: string;
  type: string;
  path: string;
}

export interface JobResultView {
  exitCode: number | null;
  stdout: string;
  stderr: string;
  log: string;
  images: JobImage[];
}

export interface Job {
  id: string;
  buildId: string;
  userId: string;
  kind: 'snapshot' | 'inspect';
  status: Status;
  request: Record<string, unknown>;
  result: JobResultView | null;
  error: JobError | null;
  progress: Progress | null;
  limits: { timeoutSeconds: number; vcpus: number };
  timings: Record<string, number> | null;
  cost: { vcpuSeconds: number; usd: number } | null;
  flags: { network?: boolean } | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export const isTerminal = (status: Status) => status === 'succeeded' || status === 'failed';

const time = (value: unknown) => (value ? new Date(value as string).toISOString() : null);

function toBuild(row: Row): Build {
  return {
    id: row.id,
    userId: row.user_id,
    parentId: row.parent_id ?? null,
    title: row.title ?? null,
    entry: row.entry ?? [],
    pythonpath: row.pythonpath ?? [],
    files: row.files ?? [],
    status: row.status,
    error: row.error ?? null,
    outputs: row.outputs ?? [],
    primary: row.primary_file ?? null,
    exportKey: row.export_key ?? null,
    exportError: row.export_error ?? null,
    thumbnailKey: row.thumbnail_key ?? null,
    log: row.log ?? '',
    progress: row.progress ?? null,
    cadgen: row.cadgen ?? null,
    limits: row.limits,
    timings: row.timings ?? null,
    cost: row.cost ?? null,
    flags: row.flags ?? null,
    createdAt: time(row.created_at)!,
    startedAt: time(row.started_at),
    finishedAt: time(row.finished_at),
  };
}

function toJob(row: Row): Job {
  return {
    id: row.id,
    buildId: row.build_id,
    userId: row.user_id,
    kind: row.kind,
    status: row.status,
    request: row.request ?? {},
    result: row.result ?? null,
    error: row.error ?? null,
    progress: row.progress ?? null,
    limits: row.limits,
    timings: row.timings ?? null,
    cost: row.cost ?? null,
    flags: row.flags ?? null,
    createdAt: time(row.created_at)!,
    startedAt: time(row.started_at),
    finishedAt: time(row.finished_at),
  };
}

const byPath = (a: { path: string }, b: { path: string }) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0);

export const encodePath = (path: string) => path.split('/').map(encodeURIComponent).join('/');

const isStep = (path: string) => /\.(step|stp)$/i.test(path);
const depthThenPath = (a: string, b: string) => a.split('/').length - b.split('/').length || (a < b ? -1 : a > b ? 1 : 0);
const stemOf = (path: string) => path.split('/').pop()!.replace(/\.[^.]*$/, '').toLowerCase();

/**
 * The file a build's link opens: the STEP named for the first entry, else the shallowest
 * STEP, else the first viewable file (shallowest, then by path). Inputs count: a build
 * that only publishes files opens one of them.
 */
export function pickPrimary(paths: string[], entry: string[]): string | null {
  const viewable = paths.filter(isViewable).sort(depthThenPath);
  const steps = viewable.filter(isStep);
  if (entry.length) {
    const named = steps.find((path) => stemOf(path) === stemOf(entry[0]));
    if (named) return named;
  }
  return steps[0] ?? viewable[0] ?? null;
}

/** The viewable files of a build, the primary first. */
export function viewsOf(paths: string[], primary: string | null): string[] {
  const viewable = paths.filter(isViewable).sort(depthThenPath);
  return primary && viewable.includes(primary) ? [primary, ...viewable.filter((path) => path !== primary)] : viewable;
}

/** `fn` over `items`, at most `limit` at a time, results in order (object-store round trips). */
export async function mapLimit<T, R>(items: T[], limit: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const results = new Array<R>(items.length);
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const index = next;
      next += 1;
      results[index] = await fn(items[index]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

const STORE_CONCURRENCY = 16;
const MAX_EXPORT_JSON = 64 * 1024 * 1024;
const PROGRESS_WRITE_MS = 3000;
const SWEEP_EVERY_MS = 60_000;

export type Service = ReturnType<typeof createService>;

export function createService(deps: Deps) {
  const { config, db, store, sandbox, clock } = deps;
  const limits = config.limits;
  const log = deps.log ?? ((message: string, extra?: Record<string, unknown>) => console.error(`[cloud] ${message}`, extra ?? ''));
  const pending = new Set<Promise<unknown>>();
  const background = (task: Promise<unknown>) => {
    const tracked = task.catch((error) => log('background task failed', { error: String(error?.stack ?? error) }));
    pending.add(tracked);
    tracked.finally(() => pending.delete(tracked));
    deps.background?.(tracked);
  };

  // --- waiting and progress --------------------------------------------------------------
  const listeners = new Map<string, Set<() => void>>();
  const progress = new Map<string, Progress>();
  const notify = (id: string) => {
    for (const listener of listeners.get(id) ?? []) listener();
  };
  async function waitFor<T extends { status: Status }>(id: string, seconds: number, read: () => Promise<T | null>): Promise<T | null> {
    const deadline = Date.now() + seconds * 1000;
    for (;;) {
      const current = await read();
      if (!current || isTerminal(current.status) || Date.now() >= deadline) return current;
      await new Promise<void>((resolve) => {
        const set = listeners.get(id) ?? new Set();
        listeners.set(id, set);
        const done = () => {
          clearTimeout(timer);
          set.delete(done);
          if (!set.size) listeners.delete(id);
          resolve();
        };
        // Poll too: on a multi-instance deployment the job runs elsewhere.
        const timer = setTimeout(done, Math.min(1000, Math.max(0, deadline - Date.now())));
        set.add(done);
      });
    }
  }

  function progressSink(table: 'builds' | 'jobs', id: string) {
    let lastWrite = 0;
    const lines: string[] = [];
    const persist = sandbox.kind !== 'local';
    return (event: RunnerEvent) => {
      const current = progress.get(id) ?? { at: iso(clock.now()) };
      if (event.type === 'log') {
        if (event.text) lines.push(event.text);
        if (lines.length > 20) lines.splice(0, lines.length - 20);
        progress.set(id, { ...current, log: [...lines], at: iso(clock.now()) });
      } else {
        progress.set(id, {
          state: event.state,
          phase: event.phase,
          entry: event.entry,
          model: event.model,
          progress: event.progress,
          elapsed: event.elapsed,
          log: [...lines],
          at: iso(clock.now()),
        });
      }
      notify(id);
      if (persist && Date.now() - lastWrite > PROGRESS_WRITE_MS) {
        lastWrite = Date.now();
        db.query(`update ${table} set progress = $2::jsonb, updated_at = $3 where id = $1 and status in ('queued', 'running')`, [id, JSON.stringify(progress.get(id)), iso(clock.now())])
          .catch(() => {});
      }
    };
  }

  // --- reads ---------------------------------------------------------------------------------
  async function getBuild(id: string): Promise<Build | null> {
    if (!isBuildId(id)) return null;
    const { rows } = await db.query('select * from builds where id = $1', [id]);
    if (!rows[0]) return null;
    const build = toBuild(rows[0]);
    if (!isTerminal(build.status)) build.progress = progress.get(id) ?? build.progress;
    return build;
  }

  async function getJob(id: string): Promise<Job | null> {
    if (!isBuildId(id)) return null;
    const { rows } = await db.query('select * from jobs where id = $1', [id]);
    if (!rows[0]) return null;
    const job = toJob(rows[0]);
    if (!isTerminal(job.status)) job.progress = progress.get(id) ?? job.progress;
    return job;
  }

  async function listBuilds(user: User, limit = 20): Promise<Build[]> {
    const { rows } = await db.query('select * from builds where user_id = $1 order by created_at desc limit $2', [user.id, Math.max(1, Math.min(100, limit))]);
    return rows.map(toBuild);
  }

  /** Every file of a build: its inputs, and its outputs (an output wins over an input it rewrote). */
  function buildFiles(build: Build): (FileRef & { kind: 'input' | 'output' })[] {
    const files = new Map<string, FileRef & { kind: 'input' | 'output' }>();
    for (const file of build.files) files.set(file.path, { ...file, kind: 'input' });
    for (const file of build.outputs) files.set(file.path, { ...file, kind: 'output' });
    return [...files.values()].sort(byPath);
  }

  async function readFile(build: Build, rawPath: string) {
    const path = normalizePath(rawPath, 'path');
    const file = buildFiles(build).find((candidate) => candidate.path === path);
    if (!file) throw notFound(`${path} is not a file of build ${build.id}`);
    const object = await store.get(objectKey(file.sha256));
    if (!object) throw new CloudError(500, 'missing_object', `${path} is missing from storage`);
    return { file, bytes: object.bytes, type: contentTypeFor(path) };
  }

  const absolute = (url: string) => (url.startsWith('/') ? `${config.publicUrl}${url}` : url);
  const objectUrl = (key: string) => absolute(store.publicUrl(key));
  const buildLink = (build: Build, path = build.primary) =>
    path ? `${config.publicUrl}/b/${build.id}/${encodePath(path)}` : `${config.publicUrl}/b/${build.id}`;

  // --- sweeping --------------------------------------------------------------------------
  let lastSweep = 0;
  function maybeSweep() {
    if (Date.now() - lastSweep < SWEEP_EVERY_MS) return;
    lastSweep = Date.now();
    background(sweep());
  }

  /**
   * Fail builds and jobs that outlived their timeout without finishing (their process died).
   * `all` fails every unfinished one: for a single-process server starting up, whose
   * earlier process cannot still be running them.
   */
  async function sweep({ all = false }: { all?: boolean } = {}): Promise<{ builds: number; jobs: number }> {
    const cutoff = iso(clock.now());
    let swept = { builds: 0, jobs: 0 };
    for (const table of ['builds', 'jobs'] as const) {
      const { rows } = await db.query(
        `select id, user_id, reservation from ${table}
         where status in ('queued', 'running')
           and ($3 or coalesce(started_at, created_at) + make_interval(secs => (limits->>'timeoutSeconds')::int + $2) < $1::timestamptz)`,
        [cutoff, limits.staleGraceSeconds, all],
      );
      for (const row of rows) {
        const error: JobError = {
          message: all ? 'The server restarted while this job ran. Run it again.' : 'This job stopped reporting before it finished and was abandoned. Run it again.',
          kind: 'infra',
        };
        const won = await db.transaction(async (tx) => {
          const { rowCount } = await tx.query(
            `update ${table} set status = 'failed', error = $2::jsonb, reservation = null, finished_at = $3, updated_at = $3
             where id = $1 and status in ('queued', 'running')`,
            [row.id, JSON.stringify(error), cutoff],
          );
          if (rowCount && row.reservation) {
            const reservation = row.reservation as Reservation;
            // Unknown usage: charge the whole reservation, the most it could have cost.
            await settle(tx, row.user_id, reservation, { vcpuSeconds: reservation.vcpuSeconds, usd: reservation.usd, wallMs: 0 }, table === 'builds' ? { builds: 1 } : { jobs: 1 });
          }
          return rowCount > 0;
        });
        if (won) {
          swept = { ...swept, [table]: swept[table] + 1 };
          notify(row.id);
        }
      }
    }
    return swept;
  }

  // --- builds ------------------------------------------------------------------------------
  async function createBuild(user: User, input: unknown): Promise<{ build: Build; deduped: boolean }> {
    maybeSweep();
    if (!input || typeof input !== 'object') throw badRequest('the request body must be a JSON object');
    const request = input as Record<string, unknown>;
    let base: Build | null = null;
    if (request.base !== undefined && request.base !== null && request.base !== '') {
      const ref = parseBuildRef(request.base);
      base = await getBuild(ref.id);
      if (!base) throw notFound(`base build ${ref.id} does not exist`);
    }
    const valid = validateBuild({ ...request, base: base?.id }, base, limits);
    const manifest: FileRef[] = [
      ...valid.kept,
      ...[...valid.added].map(([path, bytes]) => ({ path, sha256: sha256Hex(bytes), bytes: bytes.byteLength })),
    ].sort(byPath);
    const dedupeKey = sha256Hex(JSON.stringify({
      v: 1,
      files: manifest.map((file) => [file.path, file.sha256]),
      entry: valid.entry,
      pythonpath: valid.pythonpath,
      cadgen: config.cadgenVersion,
    }));
    const { rows: same } = await db.query(
      `select * from builds where user_id = $1 and dedupe_key = $2
         and (status in ('queued', 'running', 'succeeded') or (status = 'failed' and error->>'kind' = 'model'))
       order by created_at desc limit 1`,
      [user.id, dedupeKey],
    );
    if (same[0]) return { build: (await getBuild(same[0].id))!, deduped: true };

    const { rows: active } = await db.query("select id from builds where user_id = $1 and status in ('queued', 'running') limit 1", [user.id]);
    if (active[0]) throw buildInProgress(active[0].id);

    const { reservation, timeoutSeconds } = await reserve(db, limits, clock, user.id, {
      vcpus: limits.buildVcpus,
      timeoutSeconds: limits.buildTimeoutSeconds,
    });
    const id = newId();
    try {
      await mapLimit([...valid.added], STORE_CONCURRENCY, ([path, bytes]) => putObject(store, sha256Hex(bytes), bytes, contentTypeFor(path)));
      const now = iso(clock.now());
      await db.query(
        `insert into builds (id, user_id, parent_id, title, entry, pythonpath, files, dedupe_key, status, limits, reservation, created_at, updated_at)
         values ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8, 'queued', $9::jsonb, $10::jsonb, $11, $11)`,
        [
          id, user.id, base?.id ?? null, valid.title, JSON.stringify(valid.entry), JSON.stringify(valid.pythonpath),
          JSON.stringify(manifest), dedupeKey, JSON.stringify({ timeoutSeconds, vcpus: limits.buildVcpus }),
          JSON.stringify(reservation), now,
        ],
      );
    } catch (error) {
      await settle(db, user.id, reservation, null);
      if (isUniqueViolation(error, 'builds_one_active')) {
        const { rows } = await db.query("select id from builds where user_id = $1 and status in ('queued', 'running') limit 1", [user.id]);
        throw buildInProgress(rows[0]?.id ?? 'another build');
      }
      throw error;
    }
    const build = (await getBuild(id))!;
    background(runBuild(build, reservation));
    return { build, deduped: false };
  }

  function buildInProgress(id: string) {
    return new CloudError(409, 'build_in_progress', `You already have a build running (${id}): one build at a time per person. Wait for it with cad_status (or GET /v1/builds/${id}?wait=40), then send this one again.`, { cap: 'one_build_at_a_time', build: id });
  }

  async function workspaceFiles(refs: FileRef[]) {
    return mapLimit(refs, STORE_CONCURRENCY, async (file) => {
      const object = await store.get(objectKey(file.sha256));
      if (!object) throw new SandboxError(`input ${file.path} is missing from storage`);
      return { path: file.path, bytes: object.bytes };
    });
  }

  async function runBuild(build: Build, reservation: Reservation) {
    const started = clock.now();
    let usage: Usage | null = null;
    let outcome: Record<string, unknown>;
    try {
      await db.query("update builds set status = 'running', started_at = $2, updated_at = $2 where id = $1 and status = 'queued'", [build.id, iso(started)]);
      notify(build.id);
      const run = await sandbox.run({
        id: build.id,
        kind: 'build',
        request: { entry: build.entry, pythonpath: build.pythonpath, thumbnail: true },
        files: await workspaceFiles(build.files),
        timeoutSeconds: build.limits.timeoutSeconds,
        vcpus: build.limits.vcpus,
        limits: { maxCollectBytes: limits.maxOutputBytes, maxCollectFiles: limits.maxOutputFiles },
      }, { onEvent: progressSink('builds', build.id), signal: AbortSignal.timeout((build.limits.timeoutSeconds + 600) * 1000) });
      usage = usageOf(limits, build.limits.vcpus, run.usage.wallMs, run.usage.activeCpuMs);
      outcome = await ingestBuild(build, run);
      outcome.timings = { ...(outcome.timings as object), sandboxMs: run.usage.wallMs, totalMs: clock.now() - started };
    } catch (error) {
      usage ??= usageOf(limits, build.limits.vcpus, clock.now() - started);
      const detail = error instanceof SandboxError ? error.detail : '';
      log('build failed in the sandbox', { build: build.id, error: String((error as Error)?.stack ?? error) });
      outcome = {
        status: 'failed',
        error: { message: `The build could not run: ${(error as Error).message}`, kind: 'infra' },
        log: detail,
        timings: { totalMs: clock.now() - started },
      };
    }
    await finish('builds', build.id, build.userId, reservation, usage, outcome);
  }

  async function ingestBuild(build: Build, run: SandboxRun): Promise<Record<string, unknown>> {
    const result = run.result;
    if (result.kind !== 'build') throw new SandboxError('the runner answered for another kind of job');
    const collected = result.outputs.filter((path) => run.files.has(`workspace/${path}`));
    const outputs: FileRef[] = await mapLimit(collected, STORE_CONCURRENCY, async (path) => {
      const bytes = run.files.get(`workspace/${path}`)!;
      const sha256 = sha256Hex(bytes);
      await putObject(store, sha256, bytes, contentTypeFor(path));
      return { path, sha256, bytes: bytes.byteLength };
    });
    outputs.sort(byPath);
    // The primary may be an input (a sent STEP or URDF), so it is checked against every file.
    const paths = [...new Set([...build.files.map((file) => file.path), ...outputs.map((file) => file.path)])];
    const primary = result.primary && paths.includes(result.primary) && isViewable(result.primary)
      ? result.primary
      : pickPrimary(paths, build.entry);

    let exportKey: string | null = null;
    let exportError = result.exportError;
    if (result.ok && result.export) {
      try {
        exportKey = await ingestExport(build.id, run.files);
      } catch (error) {
        exportError = `the viewer export was refused: ${(error as Error).message}`;
      }
    }
    let thumbnailKey: string | null = null;
    const thumbnail = result.thumbnail ? run.files.get(result.thumbnail) : undefined;
    if (thumbnail && isPng(thumbnail)) thumbnailKey = await putObject(store, sha256Hex(thumbnail), thumbnail, 'image/png');

    return {
      status: result.ok ? 'succeeded' : 'failed',
      error: result.ok ? null : runnerError(result),
      outputs,
      primary_file: primary,
      export_key: exportKey,
      export_error: exportKey ? null : exportError,
      thumbnail_key: thumbnailKey,
      log: result.log,
      cadgen: result.cadgen,
      flags: { network: result.flags.network, dropped: result.dropped.slice(0, 100) },
      timings: { runnerMs: result.wallMs },
    };
  }

  async function ingestExport(buildId: string, files: Map<string, Uint8Array>): Promise<string> {
    const json = files.get('out/export/export.json');
    if (!json) throw new Error('export.json is missing');
    if (json.byteLength > MAX_EXPORT_JSON) throw new Error('export.json is too large');
    let index: Record<string, any>;
    try {
      index = JSON.parse(new TextDecoder().decode(json));
    } catch {
      throw new Error('export.json is not JSON');
    }
    if (!index || index.schema !== 1 || !Array.isArray(index.files) || !Array.isArray(index.views) || !index.routes || typeof index.routes !== 'object') {
      throw new Error('export.json is not a schema 1 export');
    }
    const byHash = new Map<string, Uint8Array>();
    for (const [path, bytes] of files) {
      const match = /^out\/export\/objects\/([0-9a-f]{64})$/.exec(path);
      if (!match) continue;
      if (sha256Hex(bytes) !== match[1]) throw new Error(`object ${match[1]} does not match its name`);
      byHash.set(match[1], bytes);
    }
    // No model script reaches the viewer (sanitize.ts): stripped here, outside the sandbox.
    stripModelScripts(index, byHash);
    const present = new Set(byHash.keys());
    await mapLimit([...byHash], STORE_CONCURRENCY, ([sha, bytes]) => putObject(store, sha, bytes, 'application/octet-stream'));
    for (const route of ['/__cad/asset', '/__cad/store']) {
      for (const value of Object.values((index.routes[route] ?? {}) as Record<string, any>)) {
        const sha = value?.object;
        if (typeof sha !== 'string' || !/^[0-9a-f]{64}$/.test(sha)) throw new Error(`${route} names an invalid object`);
        if (!present.has(sha) && !(await store.exists(objectKey(sha)))) throw new Error(`${route} names object ${sha}, which the export did not include`);
      }
    }
    const key = `b/${buildId}/export.json`;
    await store.put(key, new TextEncoder().encode(JSON.stringify(index)), 'application/json');
    return key;
  }

  function runnerError(result: RunnerResult): JobError {
    const error = result.error;
    if (!error) return { message: 'The job failed without saying why.', kind: 'model' };
    return { message: error.message, file: error.file ?? null, line: error.line ?? null, kind: error.kind };
  }

  /** Move a build or job to its end state and settle its reservation, once. */
  async function finish(table: 'builds' | 'jobs', id: string, userId: string, reservation: Reservation, usage: Usage | null, outcome: Record<string, unknown>) {
    const now = iso(clock.now());
    const columns: Record<string, unknown> = {
      ...outcome,
      cost: usage ? { vcpuSeconds: Math.round(usage.vcpuSeconds * 10) / 10, usd: Math.round(usage.usd * 1e6) / 1e6 } : null,
      reservation: null,
      progress: null,
      finished_at: now,
      updated_at: now,
    };
    const jsonColumns = new Set(['error', 'outputs', 'flags', 'timings', 'cost', 'reservation', 'progress', 'result']);
    const names = Object.keys(columns);
    const assignments = names.map((name, index) => `${name} = $${index + 2}${jsonColumns.has(name) ? '::jsonb' : ''}`);
    const values = names.map((name) => (jsonColumns.has(name) && columns[name] !== null ? JSON.stringify(columns[name]) : columns[name]));
    await db.transaction(async (tx) => {
      const { rowCount } = await tx.query(
        `update ${table} set ${assignments.join(', ')} where id = $1 and status in ('queued', 'running')`,
        [id, ...values],
      );
      if (rowCount) await settle(tx, userId, reservation, usage, table === 'builds' ? { builds: 1 } : { jobs: 1 });
    });
    progress.delete(id);
    notify(id);
  }

  // --- snapshot and inspection jobs ------------------------------------------------------
  async function createJob(user: User, kind: 'snapshot' | 'inspect', input: Record<string, unknown>): Promise<Job> {
    maybeSweep();
    const ref = parseBuildRef(input.build);
    const build = await getBuild(ref.id);
    if (!build) throw notFound(`build ${ref.id} does not exist`);
    if (!isTerminal(build.status)) {
      throw new CloudError(409, 'build_running', `Build ${build.id} is still ${build.status}; wait for it (cad_status) before snapshotting or inspecting it.`);
    }
    const files = buildFiles(build);
    let request: Record<string, unknown>;
    if (kind === 'snapshot') {
      const raw = input.file ?? ref.path ?? build.primary;
      if (!raw) throw badRequest(`name the file to snapshot: build ${build.id} has no viewable output`);
      const file = normalizePath(raw, 'file');
      if (!files.some((candidate) => candidate.path === file)) throw notFound(`${file} is not a file of build ${build.id}`);
      if (!isViewable(file)) throw badRequest(`${file} is not a CAD file a snapshot can render (STEP, STL, 3MF, GLB, DXF, URDF, SRDF, SDF)`);
      request = { file, format: validateFormat(input.format), args: validateSnapshotArgs(input.args) };
    } else {
      request = { code: validateCode(input.code, limits), pythonpath: build.pythonpath };
    }
    const { rows: active } = await db.query("select id from jobs where user_id = $1 and status in ('queued', 'running') limit 1", [user.id]);
    if (active[0]) throw jobInProgress(active[0].id);
    const { reservation, timeoutSeconds } = await reserve(db, limits, clock, user.id, {
      vcpus: limits.jobVcpus,
      timeoutSeconds: limits.jobTimeoutSeconds,
    });
    const id = newId();
    try {
      const now = iso(clock.now());
      await db.query(
        `insert into jobs (id, build_id, user_id, kind, status, request, limits, reservation, created_at, updated_at)
         values ($1, $2, $3, $4, 'queued', $5::jsonb, $6::jsonb, $7::jsonb, $8, $8)`,
        [id, build.id, user.id, kind, JSON.stringify(request), JSON.stringify({ timeoutSeconds, vcpus: limits.jobVcpus }), JSON.stringify(reservation), now],
      );
    } catch (error) {
      await settle(db, user.id, reservation, null);
      if (isUniqueViolation(error, 'jobs_one_active')) throw jobInProgress('another job');
      throw error;
    }
    const job = (await getJob(id))!;
    background(runJob(job, build, reservation));
    return job;
  }

  function jobInProgress(id: string) {
    return new CloudError(409, 'job_in_progress', `You already have a snapshot or inspection running (${id}): one at a time per person. Wait for it with cad_status, then try again.`, { cap: 'one_job_at_a_time', job: id });
  }

  async function runJob(job: Job, build: Build, reservation: Reservation) {
    const started = clock.now();
    let usage: Usage | null = null;
    let outcome: Record<string, unknown>;
    try {
      await db.query("update jobs set status = 'running', started_at = $2, updated_at = $2 where id = $1 and status = 'queued'", [job.id, iso(started)]);
      notify(job.id);
      const run = await sandbox.run({
        id: job.id,
        kind: job.kind,
        request: job.request,
        files: await workspaceFiles(buildFiles(build)),
        timeoutSeconds: job.limits.timeoutSeconds,
        vcpus: job.limits.vcpus,
        limits: { maxCollectBytes: 64 * 1024 * 1024, maxCollectFiles: 16 },
      }, { onEvent: progressSink('jobs', job.id), signal: AbortSignal.timeout((job.limits.timeoutSeconds + 600) * 1000) });
      usage = usageOf(limits, job.limits.vcpus, run.usage.wallMs, run.usage.activeCpuMs);
      const result = run.result;
      if (result.kind !== job.kind) throw new SandboxError('the runner answered for another kind of job');
      const images: JobImage[] = [];
      for (const path of result.images) {
        const bytes = run.files.get(path);
        const type = bytes ? imageType(bytes) : null;
        if (!bytes || !type) continue;
        const key = await putObject(store, sha256Hex(bytes), bytes, type);
        images.push({ key, url: objectUrl(key), type, path: path.replace(/^workspace\//, '') });
      }
      outcome = {
        status: result.ok ? 'succeeded' : 'failed',
        error: result.ok ? null : runnerError(result),
        result: { exitCode: result.exitCode, stdout: result.stdout, stderr: result.stderr, log: result.log, images },
        flags: { network: result.flags.network },
        timings: { runnerMs: result.wallMs, sandboxMs: run.usage.wallMs, totalMs: clock.now() - started },
      };
    } catch (error) {
      usage ??= usageOf(limits, job.limits.vcpus, clock.now() - started);
      log('job failed in the sandbox', { job: job.id, error: String((error as Error)?.stack ?? error) });
      outcome = {
        status: 'failed',
        error: { message: `The job could not run: ${(error as Error).message}`, kind: 'infra' },
        result: { exitCode: null, stdout: '', stderr: '', log: error instanceof SandboxError ? error.detail : '', images: [] },
        timings: { totalMs: clock.now() - started },
      };
    }
    await finish('jobs', job.id, job.userId, reservation, usage, outcome);
  }

  // --- viewing ---------------------------------------------------------------------------
  const exportCache = new Map<string, ExportIndex>();
  async function exportIndex(buildId: string): Promise<ExportIndex | null> {
    const cached = exportCache.get(buildId);
    if (cached) return cached;
    const build = await getBuild(buildId);
    if (!build?.exportKey) return null;
    const object = await store.get(build.exportKey);
    if (!object) return null;
    const index = JSON.parse(new TextDecoder().decode(object.bytes)) as ExportIndex;
    exportCache.set(buildId, index); // builds are immutable, so an export never goes stale
    if (exportCache.size > 64) exportCache.delete(exportCache.keys().next().value!);
    return index;
  }

  async function saveSketch(png: Uint8Array): Promise<string> {
    if (png.byteLength > 20 * 1024 * 1024) throw new CloudError(413, 'too_large', 'A sketch may be at most 20 MiB.');
    if (!isPng(png)) throw badRequest('A sketch must be a PNG image.');
    const key = `sketch/${sha256Hex(png)}.png`;
    if (!(await store.exists(key))) await store.put(key, png, 'image/png');
    return objectUrl(key);
  }

  async function requireJobOwner(user: User, id: string): Promise<Job> {
    const job = await getJob(id);
    if (!job) throw notFound(`job ${id} does not exist`);
    if (job.userId !== user.id) throw forbidden(`job ${id} belongs to someone else`);
    return job;
  }

  return {
    config,
    createBuild,
    getBuild,
    waitBuild: (id: string, seconds: number) => waitFor(id, seconds, () => getBuild(id)),
    listBuilds,
    buildFiles,
    readFile,
    createJob,
    getJob,
    requireJobOwner,
    waitJob: (id: string, seconds: number) => waitFor(id, seconds, () => getJob(id)),
    exportIndex,
    saveSketch,
    readObject: (key: string) => store.get(key),
    sweep,
    objectUrl,
    absolute,
    buildLink,
    /** Resolves when every background task started so far has finished (tests, shutdown). */
    async idle() {
      while (pending.size) await Promise.allSettled([...pending]);
    },
  };
}
