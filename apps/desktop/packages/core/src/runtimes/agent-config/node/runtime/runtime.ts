import type { Result } from '@emdash/shared';
import type { LiveLogSource } from '@emdash/wire/live';
import type { McpServer } from '#primitives/mcp/api';
import type { CatalogSkill } from '#primitives/skills/api';
import type {
  AgentConfigAuthError,
  AgentConfigMcpError,
  AgentConfigSkillsError,
  HooksStatus,
} from '#runtimes/agent-config/api';
import {
  createAgentConfigAgentsLiveHost,
  createAgentConfigAgentsModel,
  createAgentConfigMcpLiveHost,
  createAgentConfigMcpModel,
  createAgentConfigSkillsLiveHost,
  createAgentConfigSkillsModel,
  type AgentConfigAgentsLiveHost,
  type AgentConfigMcpLiveHost,
  type AgentConfigSkillsLiveHost,
} from '#runtimes/agent-config/node/state/live-models';
import type { AgentAuthStatus } from '#services/agent-plugins/api/plugins';
import { AgentHookInstaller } from '#services/agent-plugins/node';
import { AgentAuthManager, type LoginDimensions } from './auth';
import { AgentInstallManager } from './install';
import { AgentMcpConfigManager } from './mcp';
import { AgentSkillsManager } from './skills';
import type { AgentConfigRuntimeDeps } from './types';

export class AgentConfigRuntime {
  private readonly agentsModel = createAgentConfigAgentsModel();
  private readonly mcpModel = createAgentConfigMcpModel();
  private readonly skillsModel = createAgentConfigSkillsModel();
  private readonly agentsHost = createAgentConfigAgentsLiveHost(this.agentsModel);
  private readonly mcpHost = createAgentConfigMcpLiveHost(this.mcpModel);
  private readonly skillsHost = createAgentConfigSkillsLiveHost(this.skillsModel);

  readonly install: AgentInstallManager;
  readonly auth: AgentAuthManager;
  readonly mcp: AgentMcpConfigManager;
  readonly skills: AgentSkillsManager;
  private readonly hooks: AgentHookInstaller;

  constructor(private readonly deps: AgentConfigRuntimeDeps) {
    this.install = new AgentInstallManager(deps, this.agentsModel);
    this.auth = new AgentAuthManager(deps, this.install);
    this.mcp = new AgentMcpConfigManager(deps, this.mcpModel);
    this.skills = new AgentSkillsManager(deps, this.skillsModel);
    this.hooks = new AgentHookInstaller({ agentHost: deps.agentHost, logger: deps.logger });
    this.deps.scope.add(async () => {
      await this.auth.dispose();
      this.install.dispose();
      await this.agentsHost.dispose();
      await this.mcpHost.dispose();
      await this.skillsHost.dispose();
    });
    this.install.initialize();
    void this.mcp.initialize();
    void this.skills.initialize();
  }

  agentsLiveHost(): AgentConfigAgentsLiveHost {
    return this.agentsHost;
  }

  mcpLiveHost(): AgentConfigMcpLiveHost {
    return this.mcpHost;
  }

  skillsLiveHost(): AgentConfigSkillsLiveHost {
    return this.skillsHost;
  }

  async hooksStatus(providerId: string): Promise<HooksStatus> {
    const status = await this.hooks.hooksStatus(providerId);
    if (!status) throw new Error(`Provider '${providerId}' does not support hooks`);
    return status;
  }

  refreshAuthStatus(providerId: string): Promise<Result<AgentAuthStatus, AgentConfigAuthError>> {
    return this.auth.refreshAuthStatus(providerId);
  }

  startLogin(
    providerId: string,
    methodId: string,
    dimensions?: LoginDimensions
  ): Promise<Result<void, AgentConfigAuthError>> {
    return this.auth.startLogin(providerId, methodId, dimensions);
  }

  cancelLogin(providerId: string): Promise<Result<void, AgentConfigAuthError>> {
    return this.auth.cancelLogin(providerId);
  }

  sendLoginInput(providerId: string, data: string): Result<void, AgentConfigAuthError> {
    return this.auth.sendLoginInput(providerId, data);
  }

  resizeLogin(providerId: string, cols: number, rows: number): Result<void, AgentConfigAuthError> {
    return this.auth.resizeLogin(providerId, cols, rows);
  }

  markUrlHandled(providerId: string, urlId: string): Result<void, AgentConfigAuthError> {
    return this.auth.markUrlHandled(providerId, urlId);
  }

  loginOutputLog(providerId: string): LiveLogSource | null {
    return this.auth.loginOutput(providerId);
  }

  saveMcpServer(server: McpServer): Promise<Result<void, AgentConfigMcpError>> {
    return this.mcp.saveServer(server);
  }

  removeMcpServer(name: string): Promise<Result<void, AgentConfigMcpError>> {
    return this.mcp.removeServer(name);
  }

  removeMcpForAgent(providerId: string, name: string): Promise<Result<void, AgentConfigMcpError>> {
    return this.mcp.removeServerForAgent(providerId, name);
  }

  listMcpForAgent(providerId: string): Promise<Result<McpServer[], AgentConfigMcpError>> {
    return this.mcp.listForAgent(providerId);
  }

  installSkill(input: {
    skill: {
      id: string;
      installId?: string;
      skillMdContent: string;
      source?: CatalogSkill['source'];
      sourceRef?: string;
      catalogSkillId?: string;
      skillShPath?: string;
      iconUrl?: string;
    };
  }): Promise<Result<CatalogSkill[], AgentConfigSkillsError>> {
    return this.skills.installSkill(input.skill);
  }

  removeSkill(name: string): Promise<Result<CatalogSkill[], AgentConfigSkillsError>> {
    return this.skills.removeSkill(name);
  }

  createSkill(input: {
    name: string;
    description: string;
    content?: string;
  }): Promise<Result<CatalogSkill[], AgentConfigSkillsError>> {
    return this.skills.createSkill(input);
  }

  authStatusSource() {
    return {
      getStatus: (providerId: string, options?: { refresh?: boolean }) =>
        this.auth.getStatus(providerId, options),
      markUnauthenticated: (providerId: string, message?: string) =>
        this.auth.markUnauthenticated(providerId, message),
    };
  }

  dispose(): Promise<void> {
    return this.deps.scope.dispose();
  }
}
