import { runWireComponentWorker } from '@emdash/wire/worker';
import { initWorkerProcessLogging } from '@emdash/wire/worker/node';
import { workspaceRegistryComponent } from './component';

const logger = initWorkerProcessLogging('workspace-registry-runtime');
void runWireComponentWorker(workspaceRegistryComponent, { logger });
