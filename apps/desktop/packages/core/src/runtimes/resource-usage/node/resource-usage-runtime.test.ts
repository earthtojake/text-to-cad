import type { CpuInfo } from 'node:os';
import { describe, expect, it } from 'vitest';
import { cpuSnapshot, cpuUsedPercent } from './resource-usage-runtime';

function cpu(times: CpuInfo['times']): CpuInfo {
  return { model: 'test', speed: 1, times };
}

describe('resource usage CPU sampling', () => {
  it('aggregates CPU counters across cores', () => {
    expect(
      cpuSnapshot([
        cpu({ idle: 50, irq: 1, nice: 2, sys: 20, user: 27 }),
        cpu({ idle: 40, irq: 2, nice: 3, sys: 15, user: 40 }),
      ])
    ).toEqual({ idle: 90, total: 200 });
  });

  it('calculates utilization from counter deltas', () => {
    expect(cpuUsedPercent({ idle: 100, total: 200 }, { idle: 130, total: 300 })).toBe(70);
  });

  it('clamps invalid or regressing counter samples', () => {
    expect(cpuUsedPercent({ idle: 100, total: 200 }, { idle: 100, total: 200 })).toBe(0);
    expect(cpuUsedPercent({ idle: 100, total: 200 }, { idle: 250, total: 300 })).toBe(0);
  });
});
