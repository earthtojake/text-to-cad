import { closeAppDb } from '@main/db/instance';
import { startUserEnvCapture } from '@main/lib/userEnv';
import { appScope } from '../core/app-scope';
import type { AppConfig } from '../core/config';
import { step, stepOptional } from '../core/phase';
import { configureShutdownRuntimeClients } from '../shutdown';
import { configureQuitCleanupServices } from '../shutdown/phases';
import { bootBackground } from './phases/background';
import { bootControllers } from './phases/controllers';
import { bootDatabase, type DatabaseBundle } from './phases/database';
import { installGateway } from './phases/gateway';
import { bootInfrastructure } from './phases/infrastructure';
import { bootRuntimes } from './phases/runtimes';
import { bootServices } from './phases/services';

/**
 * The backend half of the window-first boot: the main window was already
 * created by the bootstrap entry (before this module's chunk even loaded), and
 * everything here runs behind it. Renderer wire traffic queues until
 * controllers register (see desktop-wire), and worker client calls queue until
 * each worker is ready.
 */
export async function finishBoot(config: AppConfig, signal?: AbortSignal): Promise<void> {
  let database: DatabaseBundle | undefined;
  try {
    throwIfBootCancelled(signal);
    // Capture runs alongside boot. Spawn-capable workers resolve through the
    // parent-owned service, whose first request awaits this in-flight capture.
    startUserEnvCapture();
    database = await step('database', () => bootDatabase(config));
    throwIfBootCancelled(signal);
    const databaseBundle = database;
    const infrastructure = await step('infrastructure', () => bootInfrastructure(databaseBundle));
    throwIfBootCancelled(signal);
    const runtimes = await step('runtimes', () => bootRuntimes(databaseBundle, infrastructure));
    throwIfBootCancelled(signal);
    const services = await step('services', () =>
      bootServices(databaseBundle, infrastructure, runtimes)
    );
    throwIfBootCancelled(signal);
    configureQuitCleanupServices({
      editorBuffers: databaseBundle.editorBuffer,
      projects: services.projects,
      pullRequests: services.pullRequestsRegistration,
      runtimes,
    });
    configureShutdownRuntimeClients(runtimes.broker, () =>
      services.hostAttachments.attachedHosts()
    );
    const controllers = await step('controllers', () =>
      bootControllers(databaseBundle, infrastructure, runtimes, services)
    );
    throwIfBootCancelled(signal);
    await step('gateway', () => installGateway(controllers, databaseBundle, services, runtimes));
    throwIfBootCancelled(signal);
    await stepOptional('background-tasks', () => bootBackground(services, runtimes));
    throwIfBootCancelled(signal);
  } catch (error) {
    try {
      await appScope.dispose(error);
    } finally {
      if (database) {
        closeAppDb();
        database.editorBuffer.dispose();
      }
    }
    throw error;
  }
}

function throwIfBootCancelled(signal?: AbortSignal): void {
  if (!signal?.aborted) return;
  throw signal.reason instanceof Error
    ? signal.reason
    : new Error('Backend bootstrap was cancelled after the renderer failed.');
}
