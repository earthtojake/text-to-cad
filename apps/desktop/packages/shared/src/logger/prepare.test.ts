import { describe, expect, it } from 'vitest';
import { secret } from '../secret';
import { REDACTED } from '../secret';
import { normalizePaths, prepareFields, serializeError } from './prepare';

describe('prepareFields', () => {
  it('replaces Secret<T> with [REDACTED]', () => {
    const result = prepareFields({ token: secret('tok_abc', 'token') });
    expect(result).toEqual({ token: REDACTED });
  });

  it('replaces nested Secret<T> with [REDACTED]', () => {
    const result = prepareFields({ user: { password: secret('hunter2') } });
    expect((result as Record<string, Record<string, unknown>>).user.password).toBe(REDACTED);
  });

  it('serializes Error instances', () => {
    const e = new Error('boom');
    const result = prepareFields({ err: e }) as Record<string, Record<string, unknown>>;
    expect(result.err.name).toBe('Error');
    expect(result.err.message).toBe('boom');
  });

  it('handles circular references', () => {
    const obj: Record<string, unknown> = { a: 1 };
    obj.self = obj;
    const result = prepareFields(obj) as Record<string, unknown>;
    expect(result.self).toBe('[Circular]');
  });

  it('passes primitives through unchanged', () => {
    expect(prepareFields('hello')).toBe('hello');
    expect(prepareFields(42)).toBe(42);
    expect(prepareFields(true)).toBe(true);
    expect(prepareFields(null)).toBeNull();
  });

  it('recurses into arrays', () => {
    const result = prepareFields([secret('x'), 'plain']) as unknown[];
    expect(result[0]).toBe(REDACTED);
    expect(result[1]).toBe('plain');
  });
});

describe('serializeError', () => {
  it('includes name, message, and stack', () => {
    const e = new Error('test error');
    const result = serializeError(e);
    expect(result.name).toBe('Error');
    expect(result.message).toBe('test error');
    expect(result.stack).toBeDefined();
  });

  it('normalizes home directory paths in stack', () => {
    const e = new Error('test');
    e.stack = `/Users/alice/code/app.ts:10`;
    const result = serializeError(e);
    expect(result.stack).toContain('/Users/~/');
    expect(result.stack).not.toContain('/Users/alice/');
  });
});

describe('normalizePaths', () => {
  it('rewrites /Users/ paths', () => {
    expect(normalizePaths('/Users/alice/code')).toBe('/Users/~/code');
  });

  it('rewrites /home/ paths', () => {
    expect(normalizePaths('/home/bob/work')).toBe('/home/~/work');
  });

  it('rewrites Windows Users paths', () => {
    expect(normalizePaths('C:\\Users\\carol\\Documents')).toBe('C:\\Users\\~\\Documents');
  });

  it('leaves other paths unchanged', () => {
    expect(normalizePaths('/var/log/app.log')).toBe('/var/log/app.log');
  });
});
