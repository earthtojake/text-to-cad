import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  classifySpawnPurpose,
  recordSpawn,
  resetSpawnCounts,
  setSpawnObserver,
  snapshotSpawnCounts,
} from './spawn-metrics';

beforeEach(() => {
  resetSpawnCounts();
  setSpawnObserver(null);
});

describe('recordSpawn / snapshotSpawnCounts', () => {
  it('accumulates counts per purpose', () => {
    recordSpawn('git');
    recordSpawn('git');
    recordSpawn('tmux');

    expect(snapshotSpawnCounts()).toEqual({ git: 2, tmux: 1 });
  });

  it('reset drains the counters so the next snapshot starts fresh', () => {
    recordSpawn('probe');
    expect(snapshotSpawnCounts({ reset: true })).toEqual({ probe: 1 });
    expect(snapshotSpawnCounts()).toEqual({});
  });

  it('notifies the observer per spawn with purpose and command', () => {
    const observer = vi.fn();
    setSpawnObserver(observer);

    recordSpawn('agent', 'claude');

    expect(observer).toHaveBeenCalledWith('agent', 'claude');
  });
});

describe('classifySpawnPurpose', () => {
  it('tags git commands and distinguishes fetch', () => {
    expect(classifySpawnPurpose('git', ['status', '--porcelain'])).toBe('git');
    expect(classifySpawnPurpose('/usr/bin/git', ['fetch', 'origin'])).toBe('fetch');
    expect(classifySpawnPurpose('git', ['-C', '/repo', 'fetch'])).toBe('fetch');
    expect(classifySpawnPurpose('git', ['-c', 'core.fsmonitor=false', 'status'])).toBe('git');
  });

  it('tags tmux and ssh executables', () => {
    expect(classifySpawnPurpose('tmux', ['list-sessions'])).toBe('tmux');
    expect(classifySpawnPurpose('/usr/bin/ssh', ['host'])).toBe('ssh');
  });

  it('handles Windows-style paths and .exe suffixes', () => {
    expect(classifySpawnPurpose('C:\\Program Files\\Git\\git.exe', ['fetch'])).toBe('fetch');
  });

  it('falls back to other for unknown executables', () => {
    expect(classifySpawnPurpose('node', ['script.js'])).toBe('other');
  });
});
