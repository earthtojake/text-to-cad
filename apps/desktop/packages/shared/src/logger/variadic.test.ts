import { describe, expect, it, vi } from 'vitest';
import type { LogFields, LogLevel, Logger } from './types';
import { createVariadicAdapter } from './variadic';

function makeStubLogger(): {
  logger: Logger;
  calls: { level: LogLevel; msg: string; fields?: LogFields }[];
} {
  const calls: { level: LogLevel; msg: string; fields?: LogFields }[] = [];

  const logger: Logger = {
    level: 'debug',
    debug: (msg, fields) => calls.push({ level: 'debug', msg, fields }),
    info: (msg, fields) => calls.push({ level: 'info', msg, fields }),
    warn: (msg, fields) => calls.push({ level: 'warn', msg, fields }),
    error: (msg, fields) => calls.push({ level: 'error', msg, fields }),
    child: () => logger,
  };

  return { logger, calls };
}

describe('createVariadicAdapter', () => {
  it('handles structured (message, fields object) call', () => {
    const { logger, calls } = makeStubLogger();
    const adapter = createVariadicAdapter(logger);
    adapter.info('test', { x: 1 });
    expect(calls).toHaveLength(1);
    expect(calls[0].msg).toBe('test');
    expect(calls[0].fields).toEqual({ x: 1 });
  });

  it('handles plain string-only call', () => {
    const { logger, calls } = makeStubLogger();
    const adapter = createVariadicAdapter(logger);
    adapter.info('just a message');
    expect(calls[0].msg).toBe('just a message');
    expect(calls[0].fields).toBeUndefined();
  });

  it('handles legacy variadic (message, error) call', () => {
    const { logger, calls } = makeStubLogger();
    const adapter = createVariadicAdapter(logger);
    const err = new Error('boom');
    adapter.error('failed:', err);
    expect(calls[0].msg).toBe('failed:');
    expect(calls[0].fields).toHaveProperty('detail');
    expect((calls[0].fields as LogFields).detail).toBe(err);
  });

  it('handles legacy variadic (message, a, b) multi-arg call', () => {
    const { logger, calls } = makeStubLogger();
    const adapter = createVariadicAdapter(logger);
    adapter.warn('multiple', 'a', 'b');
    expect(calls[0].msg).toBe('multiple');
    expect((calls[0].fields as LogFields).args).toEqual(['a', 'b']);
  });

  it('handles empty call', () => {
    const { logger, calls } = makeStubLogger();
    const adapter = createVariadicAdapter(logger);
    adapter.debug();
    expect(calls[0].msg).toBe('');
    expect(calls[0].fields).toBeUndefined();
  });

  it('passes through level from the inner logger', () => {
    const { logger } = makeStubLogger();
    const adapter = createVariadicAdapter(logger);
    expect(adapter.level).toBe('debug');
  });

  it('child() returns a new VariadicLogger wrapping inner.child', () => {
    const { logger } = makeStubLogger();
    const childCalls: unknown[] = [];
    const childLogger: Logger = {
      level: 'info',
      debug: vi.fn(),
      info: (...args) => childCalls.push(args),
      warn: vi.fn(),
      error: vi.fn(),
      child: () => childLogger,
    };
    const parent: Logger = { ...logger, child: () => childLogger };
    const adapter = createVariadicAdapter(parent);
    const child = adapter.child({ service: 'auth' });
    child.info('from child');
    expect(childCalls).toHaveLength(1);
  });

  it('does not treat an Error as a structured fields object', () => {
    const { logger, calls } = makeStubLogger();
    const adapter = createVariadicAdapter(logger);
    const err = new Error('oops');
    adapter.error('caught', err);
    // Should go through the legacy path, not treat Error as LogFields
    expect(calls[0].fields).toHaveProperty('detail');
    expect((calls[0].fields as LogFields).detail).toBe(err);
  });
});
