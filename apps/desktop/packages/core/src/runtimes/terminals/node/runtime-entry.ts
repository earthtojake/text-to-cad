import { runWireComponentWorker } from '@emdash/wire/worker';
import { initWorkerProcessLogging } from '@emdash/wire/worker/node';
import { terminalsComponent } from './component';

const logger = initWorkerProcessLogging('terminals-runtime');
void runWireComponentWorker(terminalsComponent, { logger });
