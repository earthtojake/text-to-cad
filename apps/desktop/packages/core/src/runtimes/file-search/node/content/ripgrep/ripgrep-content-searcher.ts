import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import { abortReason } from '@emdash/shared/scheduling';
import type { EnvSource } from '#primitives/exec/api';
import { parsePortableRelativePath, type PortableRelativePath } from '#primitives/path/api';
import {
  CONTENT_SEARCH_MAX_PREVIEW_LENGTH,
  type ContentSearchResult,
} from '#runtimes/file-search/api';
import { createBoundExec, type BoundExec } from '#services/exec/api';
import { DefaultFileSearchExclusions, type FileSearchExclusions } from '../../exclusions';
import { containsNativePath } from '../../native-paths';
import { errorMessage, nodeErrorCode } from '../../node-errors';
import type {
  ContentSearchContext,
  ContentSearchExecutionError,
  FileContentSearcher,
  ResolvedContentSearchInput,
} from '../content-searcher';
import { ContentSearchAccumulator } from './content-accumulator';
import { createRipgrepContentSearchArgs } from './ripgrep-args';
import { parseRipgrepJsonLine } from './ripgrep-json';
import { RipgrepJsonFramer, type RipgrepJsonFramerEvent } from './ripgrep-json-framer';

const MAX_STDERR_BYTES = 64 * 1024;
const DEFAULT_MAX_JSON_RECORD_BYTES = 32 * 1024 * 1024;

type RipgrepContentSearcherOptions = Readonly<{
  executable?: string;
  env?: EnvSource;
  exclusions: FileSearchExclusions;
  maxRecordBytes?: number;
}>;

type RipgrepRunState =
  | Readonly<{ kind: 'running' }>
  | Readonly<{ kind: 'limit' }>
  | Readonly<{ kind: 'output-error'; error: unknown }>
  | Readonly<{ kind: 'unexpected-error'; error: unknown }>;

export class RipgrepContentSearcher implements FileContentSearcher {
  private readonly executable: string;
  private readonly env: EnvSource;
  private readonly exclusions: FileSearchExclusions;
  private readonly maxRecordBytes: number;

  constructor(options: RipgrepContentSearcherOptions) {
    this.executable = options.executable ?? 'rg';
    this.env = options.env ?? (async () => process.env);
    this.exclusions = options.exclusions;
    this.maxRecordBytes = positiveSafeInteger(
      options.maxRecordBytes ?? DEFAULT_MAX_JSON_RECORD_BYTES,
      'maxRecordBytes'
    );
  }

  async search(
    input: ResolvedContentSearchInput,
    context: ContentSearchContext
  ): Promise<Result<ContentSearchResult, ContentSearchExecutionError>> {
    const executable = createBoundExec({
      file: this.executable,
      cwd: input.rootPath,
      env: this.env,
    });
    const exclusions = input.exclusions
      ? new DefaultFileSearchExclusions({ patterns: input.exclusions })
      : this.exclusions;
    return runRipgrep(executable, input, context, exclusions, this.maxRecordBytes);
  }
}

async function runRipgrep(
  executable: BoundExec,
  input: ResolvedContentSearchInput,
  context: ContentSearchContext,
  exclusions: FileSearchExclusions,
  maxRecordBytes: number
): Promise<Result<ContentSearchResult, ContentSearchExecutionError>> {
  const args = createRipgrepContentSearchArgs(input, exclusions);
  const child = await executable.spawn(args, { signal: context.signal });
  return new Promise((resolve, reject) => {
    const accumulator = new ContentSearchAccumulator(context);
    const limit = input.limit;
    const framer = new RipgrepJsonFramer({ maxRecordBytes });
    let stderr = '';
    let state: RipgrepRunState = { kind: 'running' };
    let skippedOversizedRecord = false;
    let receivedValidJsonRecord = false;
    let settled = false;

    const succeed = (result: Result<ContentSearchResult, ContentSearchExecutionError>): void => {
      if (settled) return;
      settled = true;
      resolve(result);
    };
    const crash = (error: unknown): void => {
      if (settled) return;
      settled = true;
      reject(error);
    };
    const kill = (): void => {
      try {
        child.kill();
      } catch (error) {
        state = { kind: 'unexpected-error', error };
        crash(error);
      }
    };
    const stopForOutputError = (error: unknown): void => {
      if (state.kind !== 'running') return;
      state = { kind: 'output-error', error };
      kill();
    };
    const stopForUnexpectedError = (error: unknown): void => {
      if (state.kind !== 'running') return;
      state = { kind: 'unexpected-error', error };
      kill();
    };
    const stopForLimit = (): void => {
      if (state.kind !== 'running') return;
      state = { kind: 'limit' };
      kill();
    };

    const acceptLine = (line: string): void => {
      if (!line.trim() || state.kind !== 'running') return;
      const remainingOccurrences = accumulator.remainingOccurrences(limit);
      const remainingTextLength = accumulator.remainingTextLength();
      if (remainingOccurrences === 0) {
        stopForLimit();
        return;
      }
      if (remainingTextLength === 0) {
        stopForLimit();
        return;
      }

      let match;
      try {
        match = parseRipgrepJsonLine(line, {
          maxLocations: remainingOccurrences,
          maxPreviewLength: Math.min(CONTENT_SEARCH_MAX_PREVIEW_LENGTH, remainingTextLength),
        });
        receivedValidJsonRecord = true;
        if (!match) return;
      } catch (error) {
        stopForOutputError(error);
        return;
      }

      if (match.locations.length === 0) {
        stopForLimit();
        return;
      }

      let relativePath: PortableRelativePath;
      try {
        relativePath = normalizeResultPath(input.rootPath, match.path);
      } catch (error) {
        stopForOutputError(error);
        return;
      }

      try {
        const { path: _path, locationsOmitted, ...lineMatch } = match;
        const accumulatorLimitHit = accumulator.add(relativePath, lineMatch, limit);
        if (locationsOmitted) {
          stopForLimit();
        } else if (accumulatorLimitHit) {
          stopForLimit();
        }
      } catch (error) {
        stopForUnexpectedError(error);
      }
    };

    const acceptFramerEvents = (events: readonly RipgrepJsonFramerEvent[]): void => {
      for (const event of events) {
        if (state.kind !== 'running') return;
        if (event.type === 'oversized-record') {
          skippedOversizedRecord = true;
        } else {
          acceptLine(event.line);
        }
      }
    };

    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (chunk: Buffer) => {
      if (state.kind !== 'running') return;
      try {
        acceptFramerEvents(framer.push(chunk));
      } catch (error) {
        stopForOutputError(error);
      }
    });
    child.stdout.on('error', stopForOutputError);
    child.stderr.on('data', (chunk: string) => {
      if (Buffer.byteLength(stderr) >= MAX_STDERR_BYTES) return;
      stderr += chunk;
      if (Buffer.byteLength(stderr) > MAX_STDERR_BYTES) {
        stderr = Buffer.from(stderr).subarray(0, MAX_STDERR_BYTES).toString('utf8');
      }
    });
    child.stderr.on('error', stopForUnexpectedError);
    child.on('error', (error: NodeJS.ErrnoException) => {
      if (context.signal.aborted || error.name === 'AbortError') {
        crash(abortReason(context.signal, 'Content search was cancelled'));
        return;
      }
      if (state.kind !== 'running') return;
      succeed(err(spawnError(input, error)));
    });
    child.on('close', (code) => {
      if (settled) return;
      if (context.signal.aborted) {
        crash(abortReason(context.signal, 'Content search was cancelled'));
        return;
      }
      if (settleStoppedState()) return;

      try {
        acceptFramerEvents(framer.finish());
      } catch (error) {
        stopForOutputError(error);
      }
      if (settleStoppedState()) return;

      if (code !== 0 && code !== 1) {
        if (receivedValidJsonRecord) {
          try {
            succeed(ok(accumulator.result(false)));
          } catch (error) {
            crash(error);
          }
        } else {
          succeed(err(ripgrepExitError(input, code, stderr)));
        }
        return;
      }

      try {
        succeed(ok(accumulator.result(!skippedOversizedRecord)));
      } catch (error) {
        crash(error);
      }
    });
    child.stdin.end();

    function settleStoppedState(): boolean {
      switch (state.kind) {
        case 'running':
          return false;
        case 'unexpected-error':
          crash(state.error);
          return true;
        case 'output-error':
          succeed(err(ioError(input, errorMessage(state.error, 'Unable to parse ripgrep output'))));
          return true;
        case 'limit':
          try {
            succeed(ok(accumulator.result(false)));
          } catch (error) {
            crash(error);
          }
          return true;
      }
    }
  });
}

function ripgrepExitError(
  input: ResolvedContentSearchInput,
  code: number | null,
  stderr: string
): ContentSearchExecutionError {
  const detail = stderr.trim();
  return ioError(
    input,
    detail ? `ripgrep failed: ${detail}` : `ripgrep failed with exit code ${code ?? 'unknown'}`
  );
}

function normalizeResultPath(rootPath: string, ripgrepPath: string): PortableRelativePath {
  const absolutePath = path.isAbsolute(ripgrepPath)
    ? path.resolve(ripgrepPath)
    : path.resolve(rootPath, ripgrepPath);
  if (!containsNativePath(rootPath, absolutePath)) {
    throw new Error(`ripgrep returned a path outside the registered root: ${ripgrepPath}`);
  }
  const relative = path.relative(rootPath, absolutePath).split(path.sep).join('/');
  const parsed = parsePortableRelativePath(relative);
  if (!parsed.success || parsed.data === '') {
    throw new Error(`ripgrep returned an invalid file path: ${ripgrepPath}`);
  }
  return parsed.data;
}

function spawnError(
  input: ResolvedContentSearchInput,
  error: unknown
): ContentSearchExecutionError {
  const code = nodeErrorCode(error);
  if (code === 'ENOENT') {
    return {
      type: 'content-search-unavailable',
      message: 'ripgrep is not installed or could not be found',
    };
  }
  if (code === 'EACCES' || code === 'EPERM') {
    return {
      type: 'content-search-unavailable',
      message: 'ripgrep is not executable',
    };
  }
  return ioError(input, errorMessage(error, 'Unable to start ripgrep'));
}

function ioError(input: ResolvedContentSearchInput, message: string): ContentSearchExecutionError {
  return { type: 'io', root: input.root, message };
}

function positiveSafeInteger(value: number, name: string): number {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new RangeError(`${name} must be a positive safe integer`);
  }
  return value;
}
