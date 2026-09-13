import { describe, expect, it } from 'vitest';
import { resolveModelOptionValue } from './model-option';

const advertised = [
  { id: 'default', name: 'Default (recommended)' },
  { id: 'opus[1m]', name: 'Opus (1M context)' },
  { id: 'claude-fable-5-1', name: 'Fable', description: 'Fable 5.1' },
  { id: 'claude-sonnet-5', name: 'Sonnet' },
  { id: 'claude-haiku-4-5-20251001', name: 'Haiku' },
];

describe('resolveModelOptionValue', () => {
  it('keeps an id the agent advertises verbatim', () => {
    expect(resolveModelOptionValue(advertised, 'claude-sonnet-5')).toBe('claude-sonnet-5');
    expect(resolveModelOptionValue(advertised, 'opus[1m]')).toBe('opus[1m]');
  });

  it('accepts the display name', () => {
    expect(resolveModelOptionValue(advertised, 'fable')).toBe('claude-fable-5-1');
    expect(resolveModelOptionValue(advertised, 'Opus (1M context)')).toBe('opus[1m]');
  });

  it('extends a desktop id that is a prefix of the advertised one', () => {
    expect(resolveModelOptionValue(advertised, 'claude-fable-5')).toBe('claude-fable-5-1');
    expect(resolveModelOptionValue(advertised, 'claude-haiku-4-5')).toBe(
      'claude-haiku-4-5-20251001'
    );
  });

  it('falls back to the model family when the versions differ', () => {
    expect(resolveModelOptionValue(advertised, 'claude-opus-4-8')).toBe('opus[1m]');
    expect(resolveModelOptionValue(advertised, 'claude-opus-5')).toBe('opus[1m]');
  });

  it('returns null when the agent advertises nothing comparable', () => {
    expect(resolveModelOptionValue(advertised, 'gpt-5.5')).toBeNull();
    expect(resolveModelOptionValue(advertised, '')).toBeNull();
    expect(resolveModelOptionValue([], 'claude-fable-5')).toBeNull();
  });

  it('prefers the shortest extension when several ids share the prefix', () => {
    const options = [
      { id: 'claude-sonnet-5-20260101', name: 'Sonnet (dated)' },
      { id: 'claude-sonnet-5-1', name: 'Sonnet 5.1' },
    ];
    expect(resolveModelOptionValue(options, 'claude-sonnet-5')).toBe('claude-sonnet-5-1');
  });
});
