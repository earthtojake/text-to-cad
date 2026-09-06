import type { LogLevel } from './types';

export const LEVEL_ORDER: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

export function parseLogLevel(value: string | undefined): LogLevel | undefined {
  if (!value) return undefined;
  const candidate = value.trim().toLowerCase();
  if (candidate in LEVEL_ORDER) return candidate as LogLevel;
  return undefined;
}

export function resolveLogLevel(args?: { envLevel?: string; debugFlag?: boolean }): LogLevel {
  return parseLogLevel(args?.envLevel) ?? (args?.debugFlag ? 'debug' : undefined) ?? 'warn';
}

export function isLevelEnabled(target: LogLevel, current: LogLevel): boolean {
  return LEVEL_ORDER[target] >= LEVEL_ORDER[current];
}
