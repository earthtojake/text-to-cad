import type { PluginIconVariant } from '@emdash/shared/plugins';
import { describe, expect, it } from 'vitest';
import { pickIconVariant } from '@core/primitives/agents/browser/agent-icon-variant';

const small: PluginIconVariant = { minSize: 0, light: '<svg>mark</svg>' };
const large: PluginIconVariant = { minSize: 24, light: '<svg>wordmark</svg>' };

describe('pickIconVariant', () => {
  it('returns the single variant regardless of size', () => {
    expect(pickIconVariant([small], 16)).toBe(small);
    expect(pickIconVariant([small], 64)).toBe(small);
  });

  it('picks the largest minSize that fits the rendered size', () => {
    expect(pickIconVariant([small, large], 16)).toBe(small);
    expect(pickIconVariant([small, large], 24)).toBe(large);
    expect(pickIconVariant([small, large], 48)).toBe(large);
  });

  it('is order-independent', () => {
    expect(pickIconVariant([large, small], 16)).toBe(small);
    expect(pickIconVariant([large, small], 32)).toBe(large);
  });

  it('falls back to the first variant when none fit', () => {
    const oversized: PluginIconVariant = { minSize: 24, light: '<svg></svg>' };
    expect(pickIconVariant([oversized], 16)).toBe(oversized);
  });
});
