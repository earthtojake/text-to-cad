import { describe, expect, it } from 'vitest';
import {
  collectDescendantPids,
  collectDescendantProcesses,
  parsePidPpidPairs,
  parseProcessTable,
} from './process-tree';

describe('parseProcessTable', () => {
  it('parses process identity columns from `ps` output', () => {
    const output = '  1 0 1 1 Fri Jun 19 18:28:25 2026\n  2 1 2 2 Tue Jun 23 10:04:18 2026\n';
    expect(parseProcessTable(output)).toEqual([
      {
        pid: 1,
        ppid: 0,
        pgid: 1,
        sessionId: 1,
        startTime: 'Fri Jun 19 18:28:25 2026',
      },
      {
        pid: 2,
        ppid: 1,
        pgid: 2,
        sessionId: 2,
        startTime: 'Tue Jun 23 10:04:18 2026',
      },
    ]);
  });

  it('tolerates output with only pid and ppid', () => {
    expect(parseProcessTable('  10   3\n')).toEqual([{ pid: 10, ppid: 3 }]);
  });
});

describe('parsePidPpidPairs', () => {
  it('parses `ps -o pid=,ppid=` output', () => {
    const output = '  1 0\n  2 1\n 100 2\n';
    expect(parsePidPpidPairs(output)).toEqual([
      { pid: 1, ppid: 0 },
      { pid: 2, ppid: 1 },
      { pid: 100, ppid: 2 },
    ]);
  });

  it('skips blank lines and non-numeric rows (e.g. a stray header)', () => {
    const output = 'PID PPID\n\n  10   3\n garbage line\n  11   10\n';
    expect(parsePidPpidPairs(output)).toEqual([
      { pid: 10, ppid: 3 },
      { pid: 11, ppid: 10 },
    ]);
  });

  it('returns [] for empty output', () => {
    expect(parsePidPpidPairs('')).toEqual([]);
  });
});

describe('collectDescendantProcesses', () => {
  it('preserves process metadata while collecting descendants', () => {
    const processes = [
      { pid: 200, ppid: 100, pgid: 100, sessionId: 100, startTime: 'a' },
      { pid: 300, ppid: 200, pgid: 300, sessionId: 300, startTime: 'b' },
    ];

    expect(collectDescendantProcesses(processes, [100])).toEqual(processes);
  });

  it('collects the transitive descendant tree, excluding the root', () => {
    // 100 -> 200 -> 400, 100 -> 300; 999 is unrelated.
    const pairs = [
      { pid: 200, ppid: 100 },
      { pid: 300, ppid: 100 },
      { pid: 400, ppid: 200 },
      { pid: 999, ppid: 1 },
    ];
    expect(collectDescendantProcesses(pairs, [100]).map(({ pid }) => pid)).toEqual([200, 300, 400]);
  });

  it('returns [] when the root has no children', () => {
    const pairs = [{ pid: 200, ppid: 100 }];
    expect(collectDescendantProcesses(pairs, [999])).toEqual([]);
  });

  it('supports multiple roots and never reports a root as its own descendant', () => {
    // 2 is both a root and a child of root 1: it stays excluded (it is a root),
    // while its subtree (4) and the other child (3) are collected once.
    const pairs = [
      { pid: 2, ppid: 1 },
      { pid: 3, ppid: 1 },
      { pid: 4, ppid: 2 },
    ];
    expect(collectDescendantProcesses(pairs, [1, 2]).map(({ pid }) => pid)).toEqual([3, 4]);
  });

  it('is cycle-safe (does not loop on a parent/child cycle)', () => {
    // Pathological snapshot where 100 <-> 200 reference each other.
    const pairs = [
      { pid: 200, ppid: 100 },
      { pid: 100, ppid: 200 },
    ];
    expect(collectDescendantProcesses(pairs, [100]).map(({ pid }) => pid)).toEqual([200]);
  });
});

describe('collectDescendantPids', () => {
  it('projects collected descendants to pid values', () => {
    expect(
      collectDescendantPids(
        [
          { pid: 200, ppid: 100 },
          { pid: 300, ppid: 200 },
        ],
        [100]
      )
    ).toEqual([200, 300]);
  });
});
