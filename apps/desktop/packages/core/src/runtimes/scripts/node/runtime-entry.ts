import { runWireComponentWorker } from '@emdash/wire/worker';
import { initWorkerProcessLogging } from '@emdash/wire/worker/node';
import { scriptsComponent } from './component';

const logger = initWorkerProcessLogging('scripts-runtime');
void runWireComponentWorker(scriptsComponent, { logger });
