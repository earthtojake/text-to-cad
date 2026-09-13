import { runWireComponentWorker } from '@emdash/wire/worker';
import { initWorkerProcessLogging } from '@emdash/wire/worker/node';
import { hostSettingsComponent } from './component';

const logger = initWorkerProcessLogging('host-settings-runtime');
void runWireComponentWorker(hostSettingsComponent, { logger });
