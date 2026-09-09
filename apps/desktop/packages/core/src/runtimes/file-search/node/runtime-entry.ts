import { runWireComponentWorker } from '@emdash/wire/worker';
import { initWorkerProcessLogging } from '@emdash/wire/worker/node';
import { fileSearchComponent } from './component';

const logger = initWorkerProcessLogging('file-search-runtime');
void runWireComponentWorker(fileSearchComponent, { logger });
