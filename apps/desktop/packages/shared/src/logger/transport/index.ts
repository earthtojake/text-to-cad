/**
 * Electron-agnostic file transport.
 * Provides a serialized append queue with log rotation, but has no Electron
 * imports. The app-level file-logger.ts wires in the actual log path.
 *
 * Redaction contract — secure by default:
 * - Every written line passes through `redactAll` (vendor tokens, PEM blocks,
 *   JWTs, PII patterns) unless the caller opts out. Both write paths — direct
 *   `write()` and the pino destination — honor the same hook.
 * - `redact: false` is the loud, explicit opt-out that writes raw lines
 *   (tests, debug transports).
 * - A `redact` function replaces the default entirely; it is not layered on
 *   top of `redactAll`.
 *
 * The string scan is the documented, best-effort defense for message *text*.
 * Secret-adjacent values belong in structured log fields, where all three
 * defense layers apply (`Secret` replacement, key-path redaction, and this
 * string scan); message text is prose.
 *
 * Node-only — reach it through '@emdash/shared/logger/node'.
 */

import { appendFile, mkdir, rename, stat, unlink } from 'node:fs/promises';
import { dirname } from 'node:path';
import type pinoLib from 'pino';
import { redactAll } from '../redact';

export interface FileTransportOptions {
  /**
   * Absolute path to the primary log file, or a getter that returns it lazily.
   * The getter form allows deferring Electron `app.getPath()` resolution until
   * the first write.
   */
  path: string | (() => string | undefined);
  /** Maximum size in bytes before rotating. Default: 5 MB. */
  maxBytes?: number;
  /** Number of rotated copies to retain. Default: 5. */
  retainedFiles?: number;
  /**
   * String-based redaction applied to each serialized line before writing.
   * Omitted → `redactAll` (the secure default). `false` → raw lines (explicit
   * opt-out). A function → replaces the default.
   */
  redact?: false | ((line: string) => string);
}

export interface FileTransport {
  /** Write a pre-serialized JSON string to the file. */
  write(line: string): void;
  /** Returns a promise that resolves once all pending writes complete. */
  flush(): Promise<void>;
  /** pino-compatible DestinationStream interface. */
  asDestination(): pinoLib.DestinationStream;
}

export function createFileTransport(opts: FileTransportOptions): FileTransport {
  const maxBytes = opts.maxBytes ?? 5 * 1024 * 1024;
  const retainedFiles = opts.retainedFiles ?? 5;
  const redact = opts.redact === false ? (line: string) => line : (opts.redact ?? redactAll);
  let dirReady = false;
  let pendingWrite: Promise<void> = Promise.resolve();

  function resolvePath(): string | undefined {
    return typeof opts.path === 'function' ? opts.path() : opts.path;
  }

  function enqueue(line: string): void {
    pendingWrite = pendingWrite
      .then(async () => {
        const logPath = resolvePath();
        if (!logPath) return;
        if (!dirReady) {
          await mkdir(dirname(logPath), { recursive: true });
          dirReady = true;
        }
        await rotateIfNeeded(logPath, maxBytes, retainedFiles, Buffer.byteLength(line));
        await appendFile(logPath, line, 'utf8');
      })
      .catch((error) => {
        console.error('FileTransport: write failed', error);
      });
  }

  function write(line: string): void {
    const redacted = redact(line);
    const normalized = redacted.endsWith('\n') ? redacted : `${redacted}\n`;
    enqueue(normalized);
  }

  function flush(): Promise<void> {
    return pendingWrite;
  }

  function asDestination(): pinoLib.DestinationStream {
    return {
      write(msg: string): boolean {
        const redacted = redact(msg);
        const normalized = redacted.endsWith('\n') ? redacted : `${redacted}\n`;
        enqueue(normalized);
        return true;
      },
    };
  }

  return { write, flush, asDestination };
}

async function rotateIfNeeded(
  path: string,
  maxBytes: number,
  retainedFiles: number,
  incomingBytes: number
) {
  const current = await stat(path).catch(() => undefined);
  if (!current || current.size + incomingBytes <= maxBytes) return;

  await unlink(`${path}.${retainedFiles}`).catch(() => undefined);

  for (let index = retainedFiles - 1; index >= 1; index -= 1) {
    await rename(`${path}.${index}`, `${path}.${index + 1}`).catch((error) => {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
        console.error('FileTransport: log rotation rename failed:', error);
      }
    });
  }

  await rename(path, `${path}.1`).catch((error) => {
    console.error('FileTransport: log rotation rename failed:', error);
  });
}

export function trimToLineBoundary(value: string, maxBytes: number): string {
  const encoded = Buffer.from(value, 'utf8');
  if (encoded.byteLength <= maxBytes) return value;
  const sliced = encoded.slice(-maxBytes).toString('utf8');
  const newline = sliced.indexOf('\n');
  if (newline === -1 || newline === sliced.length - 1) return sliced;
  return sliced.slice(newline + 1);
}
