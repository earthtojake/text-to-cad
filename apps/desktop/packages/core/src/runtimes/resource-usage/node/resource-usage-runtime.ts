import { statfs } from 'node:fs/promises';
import { cpus, freemem, homedir, totalmem, type CpuInfo } from 'node:os';
import type { ResourceUsageSample } from '#runtimes/resource-usage/api';

const FIRST_SAMPLE_INTERVAL_MS = 100;

export type CpuSnapshot = {
  idle: number;
  total: number;
};

export function cpuSnapshot(cpuInfo: readonly CpuInfo[]): CpuSnapshot {
  let idle = 0;
  let total = 0;
  for (const cpu of cpuInfo) {
    idle += cpu.times.idle;
    total += Object.values(cpu.times).reduce((sum, value) => sum + value, 0);
  }
  return { idle, total };
}

export function cpuUsedPercent(previous: CpuSnapshot, current: CpuSnapshot): number {
  const totalDelta = current.total - previous.total;
  const idleDelta = current.idle - previous.idle;
  if (totalDelta <= 0) return 0;
  return clampPercent(((totalDelta - idleDelta) / totalDelta) * 100);
}

export class ResourceUsageRuntime {
  private previousCpu: CpuSnapshot | undefined;
  private pendingSample: Promise<ResourceUsageSample> | undefined;

  sample(): Promise<ResourceUsageSample> {
    if (this.pendingSample) return this.pendingSample;

    const pending = this.collectSample().finally(() => {
      if (this.pendingSample === pending) this.pendingSample = undefined;
    });
    this.pendingSample = pending;
    return pending;
  }

  private async collectSample(): Promise<ResourceUsageSample> {
    let currentCpu = cpuSnapshot(cpus());
    let previousCpu = this.previousCpu;
    if (!previousCpu) {
      this.previousCpu = currentCpu;
      await delay(FIRST_SAMPLE_INTERVAL_MS);
      previousCpu = currentCpu;
      currentCpu = cpuSnapshot(cpus());
    }
    this.previousCpu = currentCpu;

    const memoryTotalBytes = totalmem();
    const memoryUsedBytes = Math.max(0, memoryTotalBytes - freemem());
    const diskPath = homedir();
    const diskStats = await statfs(diskPath);
    const diskTotalBytes = diskStats.blocks * diskStats.bsize;
    const diskAvailableBytes = diskStats.bavail * diskStats.bsize;
    const diskUsedBytes = Math.max(0, diskTotalBytes - diskAvailableBytes);

    return {
      cpu: {
        usedPercent: cpuUsedPercent(previousCpu, currentCpu),
      },
      memory: {
        usedPercent: percent(memoryUsedBytes, memoryTotalBytes),
        usedBytes: memoryUsedBytes,
        totalBytes: memoryTotalBytes,
      },
      disk: {
        usedPercent: percent(diskUsedBytes, diskTotalBytes),
        usedBytes: diskUsedBytes,
        totalBytes: diskTotalBytes,
        path: diskPath,
      },
      collectedAt: Date.now(),
    };
  }
}

function percent(used: number, total: number): number {
  if (total <= 0) return 0;
  return clampPercent((used / total) * 100);
}

function clampPercent(value: number): number {
  return Math.round(Math.min(100, Math.max(0, value)) * 10) / 10;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
