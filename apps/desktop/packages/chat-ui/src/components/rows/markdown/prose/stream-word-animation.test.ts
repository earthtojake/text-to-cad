import { describe, expect, it } from 'vitest';
import { streamWordDelayMs } from './stream-word-animation';

describe('streamWordDelayMs', () => {
  it('stagger-reveals only the appended tail and caps large provider bursts', () => {
    expect(streamWordDelayMs(8, 8)).toBe(0);
    expect(streamWordDelayMs(9, 8)).toBe(14);
    expect(streamWordDelayMs(12, 8)).toBe(56);
    expect(streamWordDelayMs(40, 8)).toBe(98);
  });

  it('never returns a negative delay for an already-settled word', () => {
    expect(streamWordDelayMs(3, 8)).toBe(0);
  });
});
