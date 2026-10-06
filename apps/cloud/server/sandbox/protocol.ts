// The server's side of the runner protocol (apps/cloud/runner/run.py), shared by every
// provider. A job directory J holds request.json, workspace/ and, afterwards, out/ and
// result.json. Everything that comes back is untrusted: the code that ran could have
// written any of it, so it is parsed strictly, sized, and checked against its digests.
import { z } from 'zod';
import { sha256Hex } from '../ids.ts';

export type JobKind = 'build' | 'snapshot' | 'inspect';

export interface SandboxFile {
  /** Relative POSIX path inside the workspace (already validated). */
  path: string;
  bytes: Uint8Array;
}

export interface SandboxJob {
  id: string;
  kind: JobKind;
  /** request.json, minus what the provider adds (kind, timeoutSeconds, vcpus, limits). */
  request: Record<string, unknown>;
  files: SandboxFile[];
  timeoutSeconds: number;
  vcpus: number;
  limits: { maxCollectBytes: number; maxCollectFiles: number };
}

export interface RunnerEvent {
  type: 'progress' | 'log';
  entry?: string;
  model?: string | null;
  state?: string;
  phase?: string | null;
  progress?: [number, number] | null;
  elapsed?: number | null;
  text?: string;
}

export interface SandboxRunOptions {
  onEvent?: (event: RunnerEvent) => void;
  signal?: AbortSignal;
}

export interface SandboxUsage {
  /** Wall time the sandbox existed for this job. */
  wallMs: number;
  /** Active CPU time, when the provider reports it. */
  activeCpuMs?: number;
}

export interface SandboxRun {
  result: RunnerResult;
  /** Collected files, keyed by their path relative to J. */
  files: Map<string, Uint8Array>;
  usage: SandboxUsage;
}

export interface SandboxProvider {
  kind: string;
  run(job: SandboxJob, options?: SandboxRunOptions): Promise<SandboxRun>;
}

/** The sandbox failed as infrastructure (no result), not because the job's code failed. */
export class SandboxError extends Error {
  detail: string;
  constructor(message: string, detail = '') {
    super(message);
    this.name = 'SandboxError';
    this.detail = detail;
  }
}

const TEXT = 64 * 1024;
const clip = (limit: number) => z.string().transform((value) => (value.length > limit ? value.slice(-limit) : value));
const jobPath = z.string().min(1).max(1024).refine(isSafeRelativePath, 'unsafe path');

export const RunnerResultSchema = z.object({
  ok: z.boolean(),
  kind: z.enum(['build', 'snapshot', 'inspect']),
  exitCode: z.number().int().nullable().catch(null),
  wallMs: z.number().nonnegative().catch(0),
  error: z
    .object({
      message: clip(4000),
      file: z.string().max(1024).nullable().optional().catch(null),
      line: z.number().int().positive().nullable().optional().catch(null),
      kind: z.enum(['model', 'timeout', 'limit', 'runner']).catch('model'),
    })
    .nullable()
    .catch(null),
  log: clip(TEXT).catch(''),
  stdout: clip(TEXT).catch(''),
  stderr: clip(TEXT).catch(''),
  outputs: z.array(jobPath).max(100_000).catch([]),
  dropped: z.array(z.string().max(1024)).max(1000).catch([]),
  primary: jobPath.nullable().catch(null),
  export: z.literal('out/export').nullable().catch(null),
  exportError: z.string().max(4000).nullable().catch(null),
  thumbnail: z.literal('out/thumbnail.png').nullable().catch(null),
  images: z.array(jobPath).max(16).catch([]),
  flags: z.object({ network: z.boolean().catch(false) }).catch({ network: false }),
  cadgen: z.string().max(64).nullable().catch(null),
  files: z.array(z.object({ path: jobPath, bytes: z.number().int().nonnegative(), sha256: z.string().regex(/^[0-9a-f]{64}$/) })).max(100_000),
});

export type RunnerResult = z.infer<typeof RunnerResultSchema>;

/** A normalized relative POSIX path: no `..`, `.`, empty or absolute parts, no NUL or backslash. */
export function isSafeRelativePath(value: string): boolean {
  if (!value || value.length > 1024 || value.startsWith('/') || value.includes('\\') || /[\u0000-\u001f]/.test(value)) return false;
  if (/^[A-Za-z]:/.test(value)) return false;
  return value.split('/').every((part) => part !== '' && part !== '.' && part !== '..');
}

export function parseRunnerResult(text: string): RunnerResult {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new SandboxError('the runner wrote a result that is not JSON');
  }
  const parsed = RunnerResultSchema.safeParse(raw);
  if (!parsed.success) throw new SandboxError(`the runner wrote an invalid result: ${parsed.error.issues[0]?.message ?? 'unknown'}`);
  return parsed.data;
}

/** The files a result asks the server to collect, checked against the job's caps. */
export function filesToCollect(result: RunnerResult, limits: SandboxJob['limits']) {
  const seen = new Set<string>();
  let total = 0;
  const wanted = [] as { path: string; bytes: number; sha256: string }[];
  for (const file of result.files) {
    if (seen.has(file.path)) continue;
    seen.add(file.path);
    if (!(file.path.startsWith('workspace/') || file.path.startsWith('out/'))) {
      throw new SandboxError(`the runner listed a file outside the job: ${file.path}`);
    }
    total += file.bytes;
    wanted.push(file);
  }
  if (wanted.length > limits.maxCollectFiles) {
    throw new SandboxError(`the job produced ${wanted.length} files; the limit is ${limits.maxCollectFiles}`);
  }
  if (total > limits.maxCollectBytes) {
    throw new SandboxError(`the job produced ${total} bytes; the limit is ${limits.maxCollectBytes}`);
  }
  return wanted;
}

/** Bytes read back from a sandbox must be exactly what the result described. */
export function checkCollected(file: { path: string; bytes: number; sha256: string }, bytes: Uint8Array): Uint8Array {
  if (bytes.byteLength !== file.bytes || sha256Hex(bytes) !== file.sha256) {
    throw new SandboxError(`${file.path} changed after the job described it`);
  }
  return bytes;
}

/** Parse one stdout line of the runner into an event, or null for anything else. */
export function parseRunnerLine(line: string): RunnerEvent | null {
  if (!line.startsWith('{') || line.length > 32 * 1024) return null;
  let value: any;
  try {
    value = JSON.parse(line);
  } catch {
    return null;
  }
  if (!value || typeof value !== 'object') return null;
  const text = (v: unknown, n = 512) => (typeof v === 'string' ? v.slice(0, n) : undefined);
  if (value.type === 'log') return { type: 'log', text: text(value.text, 16 * 1024) ?? '' };
  if (value.type !== 'progress') return null;
  const progress = Array.isArray(value.progress) && value.progress.length === 2 && value.progress.every(Number.isFinite)
    ? [Number(value.progress[0]), Number(value.progress[1])] as [number, number]
    : null;
  return {
    type: 'progress',
    entry: text(value.entry),
    model: text(value.model) ?? null,
    state: text(value.state, 32),
    phase: text(value.phase, 120) ?? null,
    progress,
    elapsed: Number.isFinite(value.elapsed) ? Number(value.elapsed) : null,
  };
}

/** Splits a byte/text stream into lines, holding a partial line until it completes. */
export function lineSplitter(onLine: (line: string) => void) {
  let pending = '';
  return {
    push(chunk: string) {
      pending += chunk;
      let index: number;
      while ((index = pending.indexOf('\n')) >= 0) {
        onLine(pending.slice(0, index).replace(/\r$/, ''));
        pending = pending.slice(index + 1);
      }
      if (pending.length > 64 * 1024) pending = pending.slice(-64 * 1024);
    },
    end() {
      if (pending) onLine(pending);
      pending = '';
    },
  };
}

/** The request.json a provider writes for a job. */
export function requestJson(job: SandboxJob): string {
  return JSON.stringify({
    ...job.request,
    kind: job.kind,
    timeoutSeconds: job.timeoutSeconds,
    vcpus: job.vcpus,
    limits: { maxOutputBytes: job.limits.maxCollectBytes, maxOutputFiles: job.limits.maxCollectFiles },
  });
}

/** Keeps the last `limit` characters of a stream. */
export function textTail(limit = 16 * 1024) {
  let text = '';
  return {
    push(chunk: string) {
      text = (text + chunk).slice(-limit);
    },
    get value() {
      return text;
    },
  };
}
