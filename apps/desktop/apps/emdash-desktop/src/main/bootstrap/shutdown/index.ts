import type { HostRef } from '@emdash/core/primitives/host/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { app, type BrowserWindow } from 'electron';
import { desktopHostEvents } from '@core/features/workbench/node';
import { getActiveSessionSummary } from '@main/host/sessions/active-session-summary';
import { updateService } from '@main/host/updates/update-service';
import { createShutdownCoordinator } from './coordinator';
import { runQuitCleanup } from './phases';

let sessionSummarySource:
  | { runtimes: RuntimeBroker; attachedHosts: () => readonly HostRef[] }
  | undefined;

const shutdownCoordinator = createShutdownCoordinator({
  emit: (event) => desktopHostEvents.emit(undefined, event),
  getActiveSessionSummary: () => {
    if (!sessionSummarySource) {
      throw new Error('Shutdown runtime clients have not been configured');
    }
    return getActiveSessionSummary(
      sessionSummarySource.runtimes,
      sessionSummarySource.attachedHosts()
    );
  },
  isInstallRequested: () => updateService.isInstallRequested,
  runCleanup: runQuitCleanup,
  exit: (code) => app.exit(code),
});

let registered = false;

export function configureShutdownRuntimeClients(
  runtimes: RuntimeBroker,
  attachedHosts: () => readonly HostRef[]
): void {
  sessionSummarySource = { runtimes, attachedHosts };
}

export function registerQuitHandler(): void {
  if (registered) return;
  registered = true;
  app.on('before-quit', (event) => {
    event.preventDefault();
    void shutdownCoordinator.handleQuitRequested();
  });
}

export function resolveQuitConfirmation(requestId: string, confirmed: boolean): void {
  shutdownCoordinator.resolveQuitConfirmation(requestId, confirmed);
}

export function ackShutdownFlush(): void {
  shutdownCoordinator.ackShutdownFlush();
}

export function markShutdownReady(): void {
  shutdownCoordinator.markShutdownReady();
}

export function watchWindow(window: BrowserWindow): void {
  shutdownCoordinator.watchWindow(window);
}

export function isShutdownInProgress(): boolean {
  return shutdownCoordinator.isShutdownInProgress();
}

export function shouldAllowWindowClose(): boolean {
  return shutdownCoordinator.state === 'shutting-down' || updateService.isInstallRequested;
}

export { createShutdownCoordinator, runQuitCleanup };
export type {
  QuitState,
  ShutdownCoordinator,
  ShutdownCoordinatorDependencies,
} from './coordinator';
