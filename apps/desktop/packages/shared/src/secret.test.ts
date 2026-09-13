import { describe, expect, it } from 'vitest';
import { REDACTED, isSecret, reveal, secret } from './secret';

describe('Secret<T>', () => {
  it('expose returns the underlying value', () => {
    const s = secret('hunter2', 'password');
    expect(s.expose()).toBe('hunter2');
  });

  it('toString returns [REDACTED]', () => {
    expect(String(secret('tok_abc', 'token'))).toBe(REDACTED);
  });

  it('toJSON returns [REDACTED]', () => {
    expect(JSON.stringify({ token: secret('tok_abc', 'token') })).toBe(`{"token":"${REDACTED}"}`);
  });

  it('template literal interpolation returns [REDACTED]', () => {
    const s = secret('super-secret');
    expect(`value: ${s}`).toBe(`value: ${REDACTED}`);
  });

  it('map transforms the inner value without exposing it', () => {
    const s = secret(42, 'number');
    const doubled = s.map((n) => n * 2);
    expect(doubled.expose()).toBe(84);
    expect(String(doubled)).toBe(REDACTED);
  });

  it('label is accessible', () => {
    expect(secret('x', 'my-label').label).toBe('my-label');
  });

  it('nodejs inspect returns redacted string (not the value)', () => {
    const s = secret('s3cr3t', 'api-key');
    const inspectKey = Symbol.for('nodejs.util.inspect.custom');
    const inspectFn = (s as unknown as { [key: symbol]: () => string })[inspectKey];
    const result = inspectFn.call(s);
    expect(result).not.toContain('s3cr3t');
    expect(result).toContain(REDACTED);
  });
});

describe('isSecret', () => {
  it('returns true for Secret instances', () => {
    expect(isSecret(secret('x'))).toBe(true);
  });

  it('returns false for plain strings', () => {
    expect(isSecret('x')).toBe(false);
  });

  it('returns false for plain objects', () => {
    expect(isSecret({ value: 'x' })).toBe(false);
  });

  it('returns false for null/undefined', () => {
    expect(isSecret(null)).toBe(false);
    expect(isSecret(undefined)).toBe(false);
  });
});

describe('reveal', () => {
  it('unwraps a Secret', () => {
    expect(reveal(secret('tok'))).toBe('tok');
  });

  it('passes plain values through unchanged', () => {
    expect(reveal('plain')).toBe('plain');
    expect(reveal(42)).toBe(42);
  });
});
