import {
  startVitalsReporting,
  type StartVitalsReportingOptions,
  type VitalsReporting,
} from '@emdash/shared/perf/node';
import { isWorkerVitalsStart, workerVitalsReport } from '../vitals';

export type WorkerVitalsPort = {
  send(message: unknown): void;
  onMessage(cb: (message: unknown) => void): void;
};

export type InstallWorkerVitalsOptions = {
  port?: WorkerVitalsPort;
  startReporting?: (options: StartVitalsReportingOptions) => VitalsReporting;
};

/**
 * Worker-side perf hookup: waits for host control messages and only then does
 * any work. A vitals start message begins self-sampling on the requested
 * cadence, sending numbers-only reports back over the IPC channel. Until a control
 * message arrives (i.e. in every unsampled or telemetry-disabled session) no
 * timers or instruments exist — just this message listener.
 */
export function installWorkerVitals(options: InstallWorkerVitalsOptions = {}): void {
  const port = options.port ?? processPort();
  if (!port) return;
  const startReporting = options.startReporting ?? startVitalsReporting;

  let reporting: VitalsReporting | null = null;
  port.onMessage((message) => {
    if (isWorkerVitalsStart(message)) {
      reporting?.dispose();
      reporting = startReporting({
        intervalMs: message.intervalMs,
        report(vitals) {
          try {
            port.send(workerVitalsReport(vitals));
          } catch {
            // Parent gone (shutdown race); vitals are best-effort.
          }
        },
      });
      return;
    }
  });
}

function processPort(): WorkerVitalsPort | null {
  if (typeof process.send !== 'function') return null;
  return {
    send(message) {
      process.send!(message);
    },
    onMessage(cb) {
      process.on('message', cb);
    },
  };
}
