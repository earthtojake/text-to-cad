import { beforeEach, describe, expect, it } from 'vitest';
import { createManualClock } from '../../testing';
import { recordSpawn, resetSpawnCounts } from '../spawn-metrics';
import {
  createVitalsSampler,
  PERF_VITALS_ALLOWED_KEYS,
  startVitalsReporting,
  type ProcessVitals,
} from './vitals';

beforeEach(() => {
  resetSpawnCounts();
});

describe('createVitalsSampler', () => {
  it('produces finite numbers under allowlisted keys only', () => {
    recordSpawn('git');
    recordSpawn('probe');
    const sampler = createVitalsSampler();
    const vitals = sampler.sample();
    sampler.dispose();

    expect(Object.keys(vitals).length).toBeGreaterThan(0);
    for (const [key, value] of Object.entries(vitals)) {
      expect(PERF_VITALS_ALLOWED_KEYS).toContain(key);
      expect(typeof value).toBe('number');
      expect(Number.isFinite(value)).toBe(true);
    }
    expect(vitals.rss_mb).toBeGreaterThan(0);
    expect(vitals.heap_used_mb).toBeGreaterThan(0);
    expect(vitals.spawns_git).toBe(1);
    expect(vitals.spawns_probe).toBe(1);
  });

  it('drains spawn counters between samples', () => {
    const sampler = createVitalsSampler();
    recordSpawn('tmux');
    expect(sampler.sample().spawns_tmux).toBe(1);
    expect(sampler.sample().spawns_tmux).toBeUndefined();
    sampler.dispose();
  });
});

describe('startVitalsReporting', () => {
  it('reports on the configured cadence and stops on dispose', async () => {
    const clock = createManualClock(0);
    const reports: ProcessVitals[] = [];
    const reporting = startVitalsReporting({
      intervalMs: 300_000,
      clock,
      report: (vitals) => reports.push(vitals),
    });

    expect(reports).toHaveLength(0);
    await clock.advanceBy(300_000);
    expect(reports).toHaveLength(1);
    expect(reports[0]!.interval_ms).toBe(300_000);

    await clock.advanceBy(300_000);
    expect(reports).toHaveLength(2);

    reporting.dispose();
    await clock.advanceBy(900_000);
    expect(reports).toHaveLength(2);
  });
});
