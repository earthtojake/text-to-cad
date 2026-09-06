import type { ResourceUsageSample } from '@emdash/core/runtimes/resource-usage/api';
import { useEffect, useState } from 'react';
import { getMachinesClient } from '@core/features/machines/api/browser/client';
import { getMachinesStore } from '@core/features/machines/contributions/app-stores';

const REFRESH_INTERVAL_MS = 5_000;

interface MetricsState {
  hostKey: string;
  metrics: ResourceUsageSample;
}

export function useMachineMetrics(
  machineId: string | undefined,
  enabled: boolean
): ResourceUsageSample | null {
  const connected = machineId ? getMachinesStore().stateFor(machineId) === 'connected' : true;
  const hostKey = machineId ?? 'local';
  const [state, setState] = useState<MetricsState | null>(null);

  useEffect(() => {
    if (!enabled || !connected) {
      setState(null);
      return;
    }

    let cancelled = false;
    const refresh = async () => {
      try {
        const client = await getMachinesClient();
        const metrics = await client.getMachineMetrics(machineId ? { machineId } : {});
        if (!cancelled) setState({ hostKey, metrics });
      } catch {
        if (!cancelled) setState(null);
      }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), REFRESH_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [connected, enabled, hostKey, machineId]);

  if (!enabled || !connected || !state || state.hostKey !== hostKey) return null;
  return state.metrics;
}
