import { createAgentConfigComponent } from '@emdash/core/runtimes/agent-config/node';
import { pluginRegistry } from '@emdash/plugins/agents';
import { runWireComponentWorker } from '@emdash/wire/worker';
import { initWorkerProcessLogging } from '@emdash/wire/worker/node';

const logger = initWorkerProcessLogging('agent-config-runtime');
void runWireComponentWorker(createAgentConfigComponent({ pluginRegistry }), { logger });
