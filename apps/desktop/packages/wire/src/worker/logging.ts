import type { Unsubscribe } from '@emdash/shared';
import type { LogFields, LogLevel, Logger } from '@emdash/shared/logger';
import type { WorkerProcess } from './types';

export type ForwardWorkerLogsOptions = {
  source?: string;
};

export function forwardWorkerLogs(
  process: WorkerProcess,
  logger: Logger,
  options: ForwardWorkerLogsOptions = {}
): Unsubscribe {
  let stderrBuffer = '';
  const unsubscribeStdio = process.onStdio((stream, chunk) => {
    if (stream === 'stdout') {
      logger.debug('runtime stdout', { source: options.source, chunk });
      return;
    }

    stderrBuffer += chunk;
    let newline = stderrBuffer.indexOf('\n');
    while (newline !== -1) {
      const line = stderrBuffer.slice(0, newline);
      stderrBuffer = stderrBuffer.slice(newline + 1);
      forwardWorkerLogLine(logger, line, options);
      newline = stderrBuffer.indexOf('\n');
    }
  });
  const unsubscribeExit = process.onExit(() => {
    if (stderrBuffer.trim()) forwardWorkerLogLine(logger, stderrBuffer, options);
    stderrBuffer = '';
  });

  return () => {
    unsubscribeStdio();
    unsubscribeExit();
  };
}

function forwardWorkerLogLine(
  logger: Logger,
  line: string,
  options: ForwardWorkerLogsOptions
): void {
  if (!line.trim()) return;
  const parsed = parseWorkerLogLine(line);
  if (!parsed) {
    logger.warn('runtime stderr', { source: options.source, chunk: line });
    return;
  }

  const { level, message, fields } = parsed;
  logger[level](message, { source: options.source, ...fields });
}

function parseWorkerLogLine(
  line: string
): { level: LogLevel; message: string; fields: LogFields } | null {
  try {
    const record = JSON.parse(line) as Record<string, unknown>;
    const level = parseRuntimeLogLevel(record.level);
    if (!level) return null;
    const message = typeof record.msg === 'string' ? record.msg : 'runtime log';
    const fields: LogFields = { ...record };
    delete fields.level;
    delete fields.msg;
    return { level, message, fields };
  } catch {
    return null;
  }
}

function parseRuntimeLogLevel(value: unknown): LogLevel | null {
  if (value === 'debug' || value === 20) return 'debug';
  if (value === 'info' || value === 30) return 'info';
  if (value === 'warn' || value === 40) return 'warn';
  if (value === 'error' || value === 50 || value === 60) return 'error';
  return null;
}
