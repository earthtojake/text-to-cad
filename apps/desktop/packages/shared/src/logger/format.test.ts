import { describe, expect, it } from 'vitest';
import { formatMessage, serializeLogValue, stringifyLogValue } from './format';

describe('serializeLogValue', () => {
  it('serializes Error to plain object', () => {
    const e = new Error('boom');
    const result = serializeLogValue(e) as Record<string, unknown>;
    expect(result.name).toBe('Error');
    expect(result.message).toBe('boom');
    expect(result).toHaveProperty('stack');
  });

  it('converts bigint to string', () => {
    expect(serializeLogValue(BigInt(42))).toBe('42');
  });

  it('converts function to "[Function name]"', () => {
    function myFn() {}
    expect(serializeLogValue(myFn)).toBe('[Function myFn]');
  });

  it('converts symbol to string', () => {
    expect(serializeLogValue(Symbol('foo'))).toBe('Symbol(foo)');
  });

  it('passes primitives through', () => {
    expect(serializeLogValue('hello')).toBe('hello');
    expect(serializeLogValue(42)).toBe(42);
    expect(serializeLogValue(null)).toBeNull();
  });

  it('serializes nested object', () => {
    const result = serializeLogValue({ a: 1, b: 'two' });
    expect(result).toEqual({ a: 1, b: 'two' });
  });
});

describe('stringifyLogValue', () => {
  it('handles circular references', () => {
    const obj: Record<string, unknown> = { a: 1 };
    obj.self = obj;
    const result = stringifyLogValue(obj);
    expect(result).toContain('[Circular]');
  });

  it('serializes Error inside an object', () => {
    const result = stringifyLogValue({ err: new Error('boom') });
    expect(result).toContain('"message":"boom"');
  });
});

describe('formatMessage', () => {
  it('joins string inputs', () => {
    expect(formatMessage(['hello', 'world'])).toBe('hello world');
  });

  it('uses error message for Error inputs', () => {
    expect(formatMessage([new Error('oops')])).toBe('oops');
  });

  it('serializes non-string non-error values', () => {
    expect(formatMessage([{ x: 1 }])).toBe('{"x":1}');
  });
});
