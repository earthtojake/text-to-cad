import type { GitTransferProgress } from '#runtimes/git/api';
import type { BoundExec, ExecResult } from '#services/exec/api';
import type { GitOperationContext } from './operation-context';

const DEFAULT_THROTTLE_MS = 250;
const PROGRESS_PHASES = new Set([
  'Counting objects',
  'Compressing objects',
  'Receiving objects',
  'Resolving deltas',
  'Writing objects',
  'Enumerating objects',
]);

export type GitTransferProgressParserOptions = {
  throttleMs?: number;
  now?: () => number;
};

export class GitTransferProgressParser {
  private readonly throttleMs: number;
  private readonly now: () => number;
  private buffer = '';
  private lastEmitAt = Number.NEGATIVE_INFINITY;
  private lastPhase: string | undefined;
  private suppressed: GitTransferProgress | undefined;

  constructor(
    private readonly onProgress: (progress: GitTransferProgress) => void,
    options: GitTransferProgressParserOptions = {}
  ) {
    this.throttleMs = options.throttleMs ?? DEFAULT_THROTTLE_MS;
    this.now = options.now ?? Date.now;
  }

  push(chunk: string): void {
    this.buffer += chunk;
    let separator = this.nextSeparator();
    while (separator) {
      const line = this.buffer.slice(0, separator.index);
      this.buffer = this.buffer.slice(separator.index + separator.length);
      this.processLine(line);
      separator = this.nextSeparator();
    }
  }

  flush(): void {
    if (this.buffer) {
      this.processLine(this.buffer);
      this.buffer = '';
    }
    if (this.suppressed) this.emit(this.suppressed);
  }

  private nextSeparator(): { index: number; length: number } | undefined {
    const cr = this.buffer.indexOf('\r');
    const lf = this.buffer.indexOf('\n');
    if (cr === -1 && lf === -1) return undefined;
    if (cr !== -1 && (lf === -1 || cr < lf)) {
      return { index: cr, length: this.buffer[cr + 1] === '\n' ? 2 : 1 };
    }
    return { index: lf, length: 1 };
  }

  private processLine(line: string): void {
    const progress = parseGitTransferProgress(line);
    if (!progress) return;

    const now = this.now();
    const phaseChanged = this.lastPhase !== undefined && progress.phase !== this.lastPhase;
    const complete = progress.percent === 100;
    if (phaseChanged || complete || now - this.lastEmitAt >= this.throttleMs) {
      this.emit(progress);
      return;
    }

    this.suppressed = progress;
  }

  private emit(progress: GitTransferProgress): void {
    this.suppressed = undefined;
    this.lastEmitAt = this.now();
    this.lastPhase = progress.phase;
    this.onProgress(progress);
  }
}

export function parseGitTransferProgress(line: string): GitTransferProgress | undefined {
  const normalized = stripRemotePrefix(line.trim());
  const match = /^([^:]+):\s*(.+)$/.exec(normalized);
  if (!match) return undefined;

  const phase = match[1]?.trim();
  const detail = match[2]?.trim();
  if (!phase || !detail || !PROGRESS_PHASES.has(phase)) return undefined;

  const percentMatch = /(\d{1,3})%/.exec(detail);
  const objectsMatch = /\((\d+)\/(\d+)\)/.exec(detail);
  return {
    phase,
    ...(percentMatch ? { percent: Number(percentMatch[1]) } : {}),
    ...(objectsMatch
      ? {
          objects: {
            done: Number(objectsMatch[1]),
            total: Number(objectsMatch[2]),
          },
        }
      : {}),
    detail,
  };
}

export async function execGitWithProgress(
  exec: BoundExec,
  args: string[],
  context: GitOperationContext<GitTransferProgress> = {}
): Promise<ExecResult> {
  const parser = context.onProgress ? new GitTransferProgressParser(context.onProgress) : undefined;
  try {
    return await exec.exec(args, {
      signal: context.signal,
      env: context.env,
      onStderr: parser ? (chunk) => parser.push(chunk) : undefined,
    });
  } finally {
    parser?.flush();
  }
}

export function throwIfGitOpAborted(signal?: AbortSignal): void {
  if (!signal?.aborted) return;
  if (signal.reason instanceof Error) throw signal.reason;
  const error = new Error('The operation was aborted');
  error.name = 'AbortError';
  throw error;
}

function stripRemotePrefix(line: string): string {
  let current = line;
  while (current.toLowerCase().startsWith('remote:')) {
    current = current.slice('remote:'.length).trimStart();
  }
  return current;
}
