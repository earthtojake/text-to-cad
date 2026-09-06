import { createController } from '@emdash/wire/rpc';
import { agentConfigContract } from '#runtimes/agent-config/api';
import type { AgentConfigRuntime } from '#runtimes/agent-config/node/runtime/runtime';
import { createAgentConfigProcedures } from './procedures';

export function createAgentConfigController(runtime: AgentConfigRuntime) {
  const procedures = createAgentConfigProcedures(runtime);
  return createController(agentConfigContract, {
    ...procedures,
    agents: runtime.agentsLiveHost(),
    loginOutput: (key) => runtime.loginOutputLog(key.providerId),
    mcpServers: runtime.mcpLiveHost(),
    skills: runtime.skillsLiveHost(),
  });
}
