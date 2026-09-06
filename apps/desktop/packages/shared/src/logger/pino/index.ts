/**
 * Node-only pino-backed Logger implementation.
 * Reach it through '@emdash/shared/logger/node' — never from the renderer bundle.
 */

import pinoLib from 'pino';
import { resolveLogLevel } from '../level';
import { prepareFields } from '../prepare';
import { DEFAULT_REDACT_PATHS } from '../redact';
import type { LogFields, LogLevel, Logger } from '../types';

export interface PinoLoggerOptions {
  envLevel?: string;
  debugFlag?: boolean;
  bindings?: LogFields;
  /**
   * pino destination stream (e.g. from createFileTransport or pino.destination).
   * Omit to use pino's default stdout transport.
   */
  destination?: pinoLib.DestinationStream;
  /**
   * Additional field paths to redact via pino/fast-redact.
   * Merged with DEFAULT_REDACT_PATHS.
   */
  extraRedactPaths?: string[];
}

export function createPinoLogger(opts: PinoLoggerOptions = {}): Logger {
  const level = resolveLogLevel({ envLevel: opts.envLevel, debugFlag: opts.debugFlag });

  const redactPaths = [...DEFAULT_REDACT_PATHS, ...(opts.extraRedactPaths ?? [])];

  const pinoOpts: pinoLib.LoggerOptions = {
    level,
    base: opts.bindings ?? {},
    timestamp: pinoLib.stdTimeFunctions.isoTime,
    redact: {
      paths: redactPaths,
      censor: '[REDACTED]',
    },
    formatters: {
      level: (label) => ({ level: label }),
    },
  };

  const pino = opts.destination ? pinoLib(pinoOpts, opts.destination) : pinoLib(pinoOpts);

  return wrapPino(pino, level);
}

function wrapPino(pino: pinoLib.Logger, level: LogLevel): Logger {
  function emit(fn: pinoLib.LogFn, message: string, fields?: LogFields): void {
    const prepared = fields ? (prepareFields(fields) as object) : undefined;
    if (prepared) {
      fn.call(pino, prepared, message);
    } else {
      fn.call(pino, message);
    }
  }

  return {
    level,
    debug: (message, fields) => emit(pino.debug.bind(pino), message, fields),
    info: (message, fields) => emit(pino.info.bind(pino), message, fields),
    warn: (message, fields) => emit(pino.warn.bind(pino), message, fields),
    error: (message, fields) => emit(pino.error.bind(pino), message, fields),
    child: (bindings) => {
      const prepared = prepareFields(bindings) as object;
      return wrapPino(pino.child(prepared), level);
    },
  };
}
