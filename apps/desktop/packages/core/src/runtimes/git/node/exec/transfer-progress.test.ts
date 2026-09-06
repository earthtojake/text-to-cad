import { describe, expect, it } from 'vitest';
import { GitTransferProgressParser, parseGitTransferProgress } from './transfer-progress';

describe('GitTransferProgressParser', () => {
  it('parses object transfer progress lines', () => {
    expect(
      parseGitTransferProgress('Receiving objects:  42% (123/292), 12.00 MiB | 1.20 MiB/s')
    ).toEqual({
      phase: 'Receiving objects',
      percent: 42,
      objects: { done: 123, total: 292 },
      detail: '42% (123/292), 12.00 MiB | 1.20 MiB/s',
    });
  });

  it('strips remote prefixes', () => {
    expect(parseGitTransferProgress('remote: Counting objects: 100% (3/3), done.')).toEqual({
      phase: 'Counting objects',
      percent: 100,
      objects: { done: 3, total: 3 },
      detail: '100% (3/3), done.',
    });
  });

  it('ignores non-progress noise', () => {
    expect(parseGitTransferProgress('fatal: Authentication failed')).toBeUndefined();
    expect(parseGitTransferProgress('remote: Total 3 (delta 0), reused 0')).toBeUndefined();
  });

  it('handles carriage-return overwritten progress and final flush', () => {
    let now = 0;
    const events: unknown[] = [];
    const parser = new GitTransferProgressParser((event) => events.push(event), {
      throttleMs: 250,
      now: () => now,
    });

    parser.push('Receiving objects:  1% (1/100)\r');
    now = 10;
    parser.push('Receiving objects:  2% (2/100)');
    parser.flush();

    expect(events).toEqual([
      {
        phase: 'Receiving objects',
        percent: 1,
        objects: { done: 1, total: 100 },
        detail: '1% (1/100)',
      },
      {
        phase: 'Receiving objects',
        percent: 2,
        objects: { done: 2, total: 100 },
        detail: '2% (2/100)',
      },
    ]);
  });

  it('does not throttle phase changes or completion', () => {
    let now = 0;
    const events: Array<{ phase: string; percent?: number }> = [];
    const parser = new GitTransferProgressParser((event) => events.push(event), {
      throttleMs: 250,
      now: () => now,
    });

    parser.push('Counting objects:  1% (1/100)\r');
    now = 10;
    parser.push('Receiving objects:  1% (1/100)\r');
    now = 20;
    parser.push('Receiving objects: 99% (99/100)\r');
    now = 30;
    parser.push('Receiving objects: 100% (100/100), done.\r');

    expect(events.map(({ phase, percent }) => ({ phase, percent }))).toEqual([
      { phase: 'Counting objects', percent: 1 },
      { phase: 'Receiving objects', percent: 1 },
      { phase: 'Receiving objects', percent: 100 },
    ]);
  });
});
