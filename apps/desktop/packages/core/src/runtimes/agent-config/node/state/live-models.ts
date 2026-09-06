import { type LeasedLiveModelProvider } from '@emdash/wire/rpc';
import { cell, expose, publishStructural, type Cell } from '@emdash/wire/state';
import type { McpServer } from '#primitives/mcp/api';
import type { CatalogSkill } from '#primitives/skills/api';
import { agentConfigContract, type AgentConfigList } from '#runtimes/agent-config/api';

export type AgentConfigAgentsLiveHost = LeasedLiveModelProvider<typeof agentConfigContract.agents>;
export type AgentConfigMcpLiveHost = LeasedLiveModelProvider<typeof agentConfigContract.mcpServers>;
export type AgentConfigSkillsLiveHost = LeasedLiveModelProvider<typeof agentConfigContract.skills>;
export type AgentConfigAgentsModel = { states: { list: Cell<AgentConfigList> } };
export type AgentConfigMcpModel = { states: { list: Cell<McpServer[]> } };
export type AgentConfigSkillsModel = { states: { list: Cell<CatalogSkill[]> } };

export function createAgentConfigAgentsLiveHost(
  model: AgentConfigAgentsModel
): AgentConfigAgentsLiveHost {
  return expose(agentConfigContract.agents, { list: model.states.list });
}

export function createAgentConfigMcpLiveHost(model: AgentConfigMcpModel): AgentConfigMcpLiveHost {
  return expose(agentConfigContract.mcpServers, { list: model.states.list });
}

export function createAgentConfigSkillsLiveHost(
  model: AgentConfigSkillsModel
): AgentConfigSkillsLiveHost {
  return expose(agentConfigContract.skills, { list: model.states.list });
}

export function createAgentConfigAgentsModel(): AgentConfigAgentsModel {
  return { states: { list: cell({} satisfies AgentConfigList) } };
}

export function createAgentConfigMcpModel(): AgentConfigMcpModel {
  return { states: { list: cell<McpServer[]>([]) } };
}

export function createAgentConfigSkillsModel(): AgentConfigSkillsModel {
  return { states: { list: cell<CatalogSkill[]>([]) } };
}

export function publishLiveModelState<T>(model: Cell<T>, next: T, previous: T | undefined): void {
  if (Object.is(previous, next)) return;
  publishStructural(model, next);
}
