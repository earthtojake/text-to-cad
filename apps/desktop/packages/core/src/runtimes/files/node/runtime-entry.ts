import { runWireComponentWorker } from '@emdash/wire/worker';
import { initWorkerProcessLogging } from '@emdash/wire/worker/node';
import { filesComponent } from './component';

const logger = initWorkerProcessLogging('files-runtime');
void runWireComponentWorker(filesComponent, { logger });
