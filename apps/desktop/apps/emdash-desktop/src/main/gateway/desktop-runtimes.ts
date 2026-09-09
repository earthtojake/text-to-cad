import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import type { Scope } from '@emdash/shared/concurrency';
import type { HostAvailabilityService } from '@core/services/hosts/node/availability';
import type {
  DesktopRuntimeClients,
  DesktopRuntimeWorkers,
  DesktopWorkersHandle,
} from './desktop-workers';

export type DesktopRuntimes = {
  readonly broker: RuntimeBroker;
  readonly clients: DesktopRuntimeClients;
  readonly hostAvailability: HostAvailabilityService;
  readonly workers: DesktopRuntimeWorkers;
  /** Activate per-worker vitals self-sampling (telemetry-sampled sessions only). */
  startWorkerVitalsSampling(intervalMs: number): void;
  dispose(): Promise<void>;
};

export function desktopRuntimes(
  workers: DesktopWorkersHandle,
  broker: RuntimeBroker,
  hostAvailability: HostAvailabilityService,
  scope: Scope
): DesktopRuntimes {
  let disposePromise: Promise<void> | undefined;
  return {
    broker,
    clients: workers.clients,
    hostAvailability,
    workers: workers.workers,
    startWorkerVitalsSampling: (intervalMs) => workers.startVitalsSampling(intervalMs),
    dispose() {
      disposePromise ??= (async () => {
        try {
          await workers.dispose();
        } finally {
          await scope.dispose();
        }
      })();
      return disposePromise;
    },
  };
}
