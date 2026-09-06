import { describe, expect, it } from 'vitest';
import { estimateThinkingTokens } from './thinking';

describe('estimateThinkingTokens', () => {
  it('returns zero when no reasoning has streamed', () => {
    expect(estimateThinkingTokens('  ')).toBe(0);
  });

  it('returns a clearly approximate byte-based count', () => {
    expect(estimateThinkingTokens('12345678')).toBe(2);
    expect(estimateThinkingTokens('a')).toBe(1);
  });

  it('counts UTF-8 bytes instead of JavaScript code units', () => {
    expect(estimateThinkingTokens('模型推理')).toBe(3);
  });
});
