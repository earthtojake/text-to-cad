import { err, ok, type Result } from '@emdash/shared';
import {
  mcpServerFieldCount,
  mcpServerToRegistration,
  registrationToMcpServer,
  type McpServer,
} from '#primitives/mcp/api';
import type { AgentConfigMcpError } from '#runtimes/agent-config/api';
import type { AgentConfigMcpModel } from '#runtimes/agent-config/node/state/live-models';
import { publishLiveModelState } from '#runtimes/agent-config/node/state/live-models';
import type { AgentConfigRuntimeDeps } from './types';

export class AgentMcpConfigManager {
  private writeLock = Promise.resolve();
  private list: McpServer[] = [];

  constructor(
    private readonly deps: AgentConfigRuntimeDeps,
    private readonly model: AgentConfigMcpModel
  ) {}

  async initialize(): Promise<void> {
    await this.refresh();
  }

  async refresh(): Promise<McpServer[]> {
    const installed = await this.readAll();
    this.publish(installed);
    return installed;
  }

  async saveServer(server: McpServer): Promise<Result<void, AgentConfigMcpError>> {
    if (!server.name || !/^[\w\-._]+$/.test(server.name)) {
      return err({ type: 'invalid-state', message: `Invalid server name: "${server.name}"` });
    }
    for (const providerId of server.providers) {
      if (!this.deps.agentHost.get(providerId))
        return err({ type: 'unknown-provider', providerId });
    }
    try {
      return await this.withWriteLock(async () => {
        const selectedProviders = new Set(server.providers);
        for (const provider of this.getMcpProviders()) {
          const agentId = provider.metadata.id;
          const read = await this.deps.agentHost.readMcpServers(agentId);
          let regs = read.success ? read.data : [];
          const idx = regs.findIndex((reg) => reg.name === server.name);
          if (selectedProviders.has(agentId)) {
            const next = mcpServerToRegistration(server);
            if (idx >= 0) regs[idx] = next;
            else regs = [...regs, next];
          } else if (idx >= 0) {
            regs.splice(idx, 1);
          }
          const write = await this.deps.agentHost.writeMcpServers(agentId, regs);
          if (!write.success) throw new Error(agentHostErrorMessage(write.error));
        }
        await this.refresh();
        return ok();
      });
    } catch (error) {
      return err(toIoError(error));
    }
  }

  async removeServer(name: string): Promise<Result<void, AgentConfigMcpError>> {
    try {
      return await this.withWriteLock(async () => {
        for (const provider of this.getMcpProviders()) {
          const result = await this.deps.agentHost.removeMcpServer(provider.metadata.id, name);
          if (!result.success) throw new Error(agentHostErrorMessage(result.error));
        }
        await this.refresh();
        return ok();
      });
    } catch (error) {
      return err(toIoError(error));
    }
  }

  async removeServerForAgent(
    providerId: string,
    name: string
  ): Promise<Result<void, AgentConfigMcpError>> {
    const provider = this.deps.agentHost.get(providerId);
    if (!provider) return err({ type: 'unknown-provider', providerId });
    if (provider.capabilities.mcp.kind !== 'supported' || !provider.behavior.mcp) {
      return err({
        type: 'invalid-state',
        message: `Provider '${providerId}' does not support MCP`,
      });
    }

    try {
      return await this.withWriteLock(async () => {
        const result = await this.deps.agentHost.removeMcpServer(providerId, name);
        if (!result.success) throw new Error(agentHostErrorMessage(result.error));
        await this.refresh();
        return ok();
      });
    } catch (error) {
      return err(toIoError(error));
    }
  }

  async listForAgent(providerId: string): Promise<Result<McpServer[], AgentConfigMcpError>> {
    const provider = this.deps.agentHost.get(providerId);
    if (!provider) return err({ type: 'unknown-provider', providerId });
    if (provider.capabilities.mcp.kind !== 'supported' || !provider.behavior.mcp) return ok([]);
    try {
      const result = await this.deps.agentHost.readMcpServers(providerId);
      if (!result.success) return err(toIoError(agentHostErrorMessage(result.error)));
      const regs = result.data;
      return ok(regs.map((reg) => registrationToMcpServer(reg, [providerId])));
    } catch (error) {
      return err(toIoError(error));
    }
  }

  private async readAll(): Promise<McpServer[]> {
    const serversByName = new Map<string, { server: McpServer; providers: Set<string> }>();
    for (const provider of this.getMcpProviders()) {
      const agentId = provider.metadata.id;
      const result = await this.deps.agentHost.readMcpServers(agentId);
      if (!result.success) {
        this.deps.logger.warn(`Failed to read MCP config for ${agentId}:`, {
          error: agentHostErrorMessage(result.error),
        });
        continue;
      }
      for (const reg of result.data) {
        const server = registrationToMcpServer(reg, [agentId]);
        const existing = serversByName.get(reg.name);
        if (existing) {
          existing.providers.add(agentId);
          if (mcpServerFieldCount(server) > mcpServerFieldCount(existing.server)) {
            existing.server = server;
          }
        } else {
          serversByName.set(reg.name, { server, providers: new Set([agentId]) });
        }
      }
    }

    const installed: McpServer[] = [];
    for (const { server, providers } of serversByName.values()) {
      installed.push({ ...server, providers: Array.from(providers) });
    }
    return installed;
  }

  private getMcpProviders() {
    return this.deps.agentHost
      .getAll()
      .filter(
        (provider) => provider.capabilities.mcp.kind === 'supported' && provider.behavior.mcp
      );
  }

  private async withWriteLock<T>(fn: () => Promise<T>): Promise<T> {
    const prev = this.writeLock;
    let release: () => void;
    this.writeLock = new Promise<void>((resolve) => {
      release = resolve;
    });
    await prev;
    try {
      return await fn();
    } finally {
      release!();
    }
  }

  private publish(list: McpServer[]): void {
    const previous = this.list;
    this.list = list;
    publishLiveModelState(this.model.states.list, list, previous);
  }
}

function toIoError(error: unknown): AgentConfigMcpError {
  return { type: 'io', message: error instanceof Error ? error.message : String(error) };
}

function agentHostErrorMessage(error: { type: string; message?: string }): string {
  return error.message ?? error.type;
}
