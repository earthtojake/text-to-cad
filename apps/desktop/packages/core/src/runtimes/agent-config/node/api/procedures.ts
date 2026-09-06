import { ok, type Result } from '@emdash/shared';
import type { McpServer } from '#primitives/mcp/api';
import type { CatalogSkill } from '#primitives/skills/api';
import type {
  AgentConfigAuthError,
  AgentConfigMcpError,
  AgentConfigSkillsError,
  HooksStatus,
} from '#runtimes/agent-config/api';
import type { AgentConfigRuntime } from '#runtimes/agent-config/node/runtime/runtime';
import type { AgentAuthStatus } from '#services/agent-plugins/api/plugins';

export function createAgentConfigProcedures(runtime: AgentConfigRuntime) {
  return {
    hooksStatus(input: { providerId: string }): Promise<HooksStatus> {
      return runtime.hooksStatus(input.providerId);
    },
    startLogin(input: {
      providerId: string;
      methodId: string;
      cols?: number;
      rows?: number;
    }): Promise<Result<void, AgentConfigAuthError>> {
      const dimensions =
        input.cols !== undefined && input.rows !== undefined
          ? { cols: input.cols, rows: input.rows }
          : undefined;
      return runtime.startLogin(input.providerId, input.methodId, dimensions);
    },
    cancelLogin(input: { providerId: string }): Promise<Result<void, AgentConfigAuthError>> {
      return runtime.cancelLogin(input.providerId);
    },
    sendLoginInput(input: {
      providerId: string;
      data: string;
    }): Result<void, AgentConfigAuthError> {
      return runtime.sendLoginInput(input.providerId, input.data);
    },
    resizeLogin(input: {
      providerId: string;
      cols: number;
      rows: number;
    }): Result<void, AgentConfigAuthError> {
      return runtime.resizeLogin(input.providerId, input.cols, input.rows);
    },
    markUrlHandled(input: {
      providerId: string;
      urlId: string;
    }): Result<void, AgentConfigAuthError> {
      return runtime.markUrlHandled(input.providerId, input.urlId);
    },
    refreshAuthStatus(input: {
      providerId: string;
    }): Promise<Result<AgentAuthStatus, AgentConfigAuthError>> {
      return runtime.refreshAuthStatus(input.providerId);
    },
    saveMcpServer(input: { server: McpServer }): Promise<Result<void, AgentConfigMcpError>> {
      return runtime.saveMcpServer(input.server);
    },
    removeMcpServer(input: { name: string }): Promise<Result<void, AgentConfigMcpError>> {
      return runtime.removeMcpServer(input.name);
    },
    removeMcpForAgent(input: {
      providerId: string;
      name: string;
    }): Promise<Result<void, AgentConfigMcpError>> {
      return runtime.removeMcpForAgent(input.providerId, input.name);
    },
    async listMcpForAgent(input: {
      providerId: string;
    }): Promise<Result<{ servers: McpServer[] }, AgentConfigMcpError>> {
      const listed = await runtime.listMcpForAgent(input.providerId);
      return listed.success ? ok({ servers: listed.data }) : listed;
    },
    async installSkill(
      input: Parameters<AgentConfigRuntime['installSkill']>[0]
    ): Promise<Result<{ skills: CatalogSkill[] }, AgentConfigSkillsError>> {
      const installed = await runtime.installSkill(input);
      return installed.success ? ok({ skills: installed.data }) : installed;
    },
    async removeSkill(input: {
      name: string;
    }): Promise<Result<{ skills: CatalogSkill[] }, AgentConfigSkillsError>> {
      const removed = await runtime.removeSkill(input.name);
      return removed.success ? ok({ skills: removed.data }) : removed;
    },
    async createSkill(
      input: Parameters<AgentConfigRuntime['createSkill']>[0]
    ): Promise<Result<{ skills: CatalogSkill[] }, AgentConfigSkillsError>> {
      const created = await runtime.createSkill(input);
      return created.success ? ok({ skills: created.data }) : created;
    },
  };
}

export type AgentConfigProcedures = ReturnType<typeof createAgentConfigProcedures>;
