import type { McpServer as AcpMcpServer } from '@agentclientprotocol/sdk';
import type { McpServerRegistration } from '#primitives/mcp/api';

export interface AcpMcpCapabilities {
  http: boolean;
  sse: boolean;
}

export interface SessionMcpServerSummary {
  name: string;
  transport: 'stdio' | 'http' | 'sse';
}

export function registrationsToAcpMcpServers(
  registrations: readonly McpServerRegistration[],
  capabilities: AcpMcpCapabilities
): AcpMcpServer[] {
  const servers: AcpMcpServer[] = [];

  for (const registration of registrations) {
    const server = registrationToAcpMcpServer(registration, capabilities);
    if (server) servers.push(server);
  }

  return servers;
}

export function summarizeAcpMcpServers(
  servers: readonly AcpMcpServer[]
): SessionMcpServerSummary[] {
  return servers.map((server) => ({
    name: server.name,
    transport: 'type' in server && server.type !== 'acp' ? server.type : 'stdio',
  }));
}

function registrationToAcpMcpServer(
  registration: McpServerRegistration,
  capabilities: AcpMcpCapabilities
): AcpMcpServer | null {
  if (registration.enabled === false) return null;

  const transport = resolveTransport(registration);
  if (transport === 'http') {
    if (!capabilities.http || typeof registration.url !== 'string') return null;
    return {
      type: 'http',
      name: registration.name,
      url: registration.url,
      headers: recordToPairs(registration.headers),
    };
  }

  if (transport === 'sse') {
    if (!capabilities.sse || typeof registration.url !== 'string') return null;
    return {
      type: 'sse',
      name: registration.name,
      url: registration.url,
      headers: recordToPairs(registration.headers),
    };
  }

  if (typeof registration.command !== 'string') return null;
  return {
    name: registration.name,
    command: registration.command,
    args: Array.isArray(registration.args) ? registration.args : [],
    env: recordToPairs(registration.env),
  };
}

function resolveTransport(registration: McpServerRegistration): 'stdio' | 'http' | 'sse' {
  if (registration.type === 'sse') return 'sse';
  if (
    registration.transport === 'http' ||
    registration.type === 'http' ||
    (typeof registration.url === 'string' && typeof registration.command !== 'string')
  ) {
    return 'http';
  }
  return 'stdio';
}

function recordToPairs(record: Record<string, string> | undefined) {
  return Object.entries(record ?? {}).map(([name, value]) => ({ name, value }));
}
