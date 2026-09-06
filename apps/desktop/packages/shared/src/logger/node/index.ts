/**
 * Node-only logger surface: process logging bootstrap, the pino-backed Logger,
 * the file transport, and the AsyncLocalStorage log context.
 * Import from '@emdash/shared/logger/node' in Node deployments only.
 */

import pinoLib from 'pino';
import { setRootLogger } from '../context';
import { installAsyncLogContext } from '../context-node';
import { createPinoLogger } from '../pino';
import type { LogFields, Logger } from '../types';

export { installAsyncLogContext } from '../context-node';
export { createPinoLogger, type PinoLoggerOptions } from '../pino';
export {
  createFileTransport,
  trimToLineBoundary,
  type FileTransport,
  type FileTransportOptions,
} from '../transport';

export type InitProcessLoggingOptions = {
  name: string;
  env?: NodeJS.ProcessEnv;
  bindings?: LogFields;
  destination?: pinoLib.DestinationStream;
  debugFlag?: boolean;
};

export function initProcessLogging(options: InitProcessLoggingOptions): Logger {
  const env = options.env ?? process.env;
  const logger = createPinoLogger({
    envLevel: env.EMDASH_LOG_LEVEL ?? env.LOG_LEVEL,
    debugFlag: options.debugFlag,
    bindings: {
      proc: options.name,
      pid: process.pid,
      ...options.bindings,
    },
    destination: options.destination ?? pinoLib.destination(2),
  });

  installAsyncLogContext();
  setRootLogger(logger);
  return logger;
}
