export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export type LogFields = Record<string, unknown>;

/**
 * Canonical Logger interface — strict structured API.
 * Every log call takes a static message and optional fields object.
 * Use child() to bind permanent context to a named subsystem.
 */
export interface Logger {
  readonly level: LogLevel;
  debug(message: string, fields?: LogFields): void;
  info(message: string, fields?: LogFields): void;
  warn(message: string, fields?: LogFields): void;
  error(message: string, fields?: LogFields): void;
  /** Return a new Logger with additional permanent context bindings. */
  child(bindings: LogFields): Logger;
}
