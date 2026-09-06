import { runWireComponentWorker } from '@emdash/wire/worker';
import { initWorkerProcessLogging } from '@emdash/wire/worker/node';
import { resourceUsageComponent } from './component';

const logger = initWorkerProcessLogging('resource-usage-runtime');
void runWireComponentWorker(resourceUsageComponent, { logger });
