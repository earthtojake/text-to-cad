import { runWireComponentWorker } from '@emdash/wire/worker';
import { initWorkerProcessLogging } from '@emdash/wire/worker/node';
import { conversationsComponent } from './component';

const logger = initWorkerProcessLogging('conversations-runtime');
void runWireComponentWorker(conversationsComponent, { logger });
