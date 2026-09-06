import { runWireComponentWorker } from '@emdash/wire/worker';
import { initWorkerProcessLogging } from '@emdash/wire/worker/node';
import { fsWatchComponent } from './component';

const logger = initWorkerProcessLogging('fs-watch-runtime');
void runWireComponentWorker(fsWatchComponent, { logger });
