import { runWireComponentWorker } from '@emdash/wire/worker';
import { initWorkerProcessLogging } from '@emdash/wire/worker/node';
import { gitComponent } from './component';

const logger = initWorkerProcessLogging('git-runtime');
void runWireComponentWorker(gitComponent, { logger });
