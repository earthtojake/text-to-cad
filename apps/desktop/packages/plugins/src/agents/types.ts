declare const agentProviderIdBrand: unique symbol;

export type AgentProviderId = string & { readonly [agentProviderIdBrand]?: 'AgentProviderId' };

export function asAgentProviderId(id: string): AgentProviderId {
  return id as AgentProviderId;
}
