import type { EditorBufferService } from '@core/features/editor/node/editor-buffer-service';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import type { PullRequestsRegistration } from '@core/services/pull-requests/node/pull-requests-registration';
import { acpAgentStatusBridge } from '@main/core/acp/agent-status-bridge';
import { agentStatusService } from '@main/core/agent-status/agent-status-service';
import { tuiAgentStatusBridge } from '@main/core/agent-status/tui-agent-status-bridge';
import { closeAppDb } from '@main/db/instance';
import { updateService } from '@main/host/updates/update-service';
import { log } from '@main/lib/logger';
import { telemetryService } from '@main/lib/telemetry';
import { appScope } from '../core/app-scope';
import { runPhase, type Phase } from '../core/phase';
import { disposeNotificationService } from '../core/service-instances';

const CRITICAL_DEADLINE_MS = 5_000;
const GRACE_WINDOW_MS = 400;

type QuitCleanupServices = {
  editorBuffers: Pick<EditorBufferService, 'dispose'>;
  projects: Pick<ProjectAttachmentManager, 'dispose' | 'release'>;
  pullRequests: Pick<PullRequestsRegistration, 'dispose'>;
  runtimes: { dispose(): Promise<void> };
};

let cleanupServices: QuitCleanupServices | undefined;

export function configureQuitCleanupServices(services: QuitCleanupServices): void {
  cleanupServices = services;
}

function criticalPhases(services: QuitCleanupServices): Phase<void>[] {
  return [
    {
      name: 'acp-agent-status-bridge',
      run: async () => acpAgentStatusBridge.dispose(),
    },
    {
      name: 'tui-agent-status-bridge',
      run: async () => tuiAgentStatusBridge.dispose(),
    },
    {
      name: 'agent-status-service',
      run: async () => agentStatusService.dispose(),
    },
    {
      name: 'project-manager-release',
      run: () => services.projects.release(),
    },
    {
      name: 'desktop-wire-workers',
      run: () => services.runtimes.dispose(),
    },
    {
      name: 'app-scope',
      run: () => appScope.dispose(),
    },
    {
      name: 'database',
      run: () => closeAppDb(),
    },
    {
      name: 'editor-buffers',
      run: async () => services.editorBuffers.dispose(),
    },
    {
      name: 'telemetry-service',
      run: () => telemetryService.dispose(),
    },
  ];
}

function bestEffortPhases(services: QuitCleanupServices): Phase<void>[] {
  return [
    {
      name: 'project-manager-dispose',
      run: () => services.projects.dispose(),
    },
  ];
}

export async function runQuitCleanup(): Promise<void> {
  const services = cleanupServices;
  if (!services) throw new Error('Quit cleanup services were not configured');
  telemetryService.capture('app_closed');

  updateService.dispose();
  disposeNotificationService();
  services.pullRequests.dispose();

  await withDeadline(runCriticalPhases(services), CRITICAL_DEADLINE_MS).catch((error: unknown) => {
    log.error('quit: critical cleanup failed or timed out', error);
  });

  const graceful = Promise.allSettled(
    bestEffortPhases(services).map((phase) => runPhase(phase, undefined))
  );
  await Promise.race([graceful, delay(GRACE_WINDOW_MS)]);
}

async function runCriticalPhases(services: QuitCleanupServices): Promise<void> {
  for (const phase of criticalPhases(services)) {
    try {
      await runPhase(phase, undefined);
    } catch (error) {
      log.error(`quit: critical phase ${phase.name} failed`, error);
    }
  }
}

async function withDeadline<T>(promise: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  void promise.catch(() => undefined);
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`Timed out after ${ms}ms`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
