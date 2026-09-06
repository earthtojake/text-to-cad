import { err, ok, type Result } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import type { PluginRegistry } from '@emdash/shared/plugins';
import { compose, deduplicate } from '@emdash/shared/requests';
import { buildAllowlistedAgentEnv } from '#primitives/agent-env/api';
import type { EnvSource, IExecutionContext } from '#primitives/exec/api';
import type { HostDependencyResolver, Platform } from '#primitives/host-dependencies/api';
import type { PluginFs } from '#primitives/plugin-fs/api';
import type {
  AcpSpawnResult,
  IAcpBehavior,
} from '#services/agent-plugins/api/plugins/capabilities/acp';
import type {
  AgentAuthDescriptor,
  AgentAuthStatus,
  IAgentAuthBehavior,
} from '#services/agent-plugins/api/plugins/capabilities/auth';
import type { McpServerRegistration } from '#services/agent-plugins/api/plugins/capabilities/mcp';
import type {
  AgentCommand,
  CommandContext,
} from '#services/agent-plugins/api/plugins/capabilities/prompt';
import {
  createSpawnContextResolver,
  type SpawnContext,
  type SpawnContextError,
  type SpawnContextResolver,
} from '#services/agent-plugins/api/spawn-context';
import type { ConfigRootContext } from './helpers/config-root';
import type { CLIAgentPluginProvider } from './index';

export type ResolvedAcpProvider = {
  behavior: IAcpBehavior;
};

export type ResolvedAuthProvider = {
  name: string;
  auth: AgentAuthDescriptor;
  behavior?: IAgentAuthBehavior;
};

export type ResolvedTuiProvider = {
  name: string;
  prompt: CLIAgentPluginProvider['capabilities']['prompt'];
  hooks: CLIAgentPluginProvider['capabilities']['hooks'];
  buildCommand: NonNullable<CLIAgentPluginProvider['behavior']['prompt']>['buildCommand'];
  parseHookEvent?: NonNullable<CLIAgentPluginProvider['behavior']['hooks']>['parseHookEvent'];
  validateSessionId?: NonNullable<
    CLIAgentPluginProvider['behavior']['sessions']
  >['validateSessionId'];
};

export type AgentHostDeps = {
  scope: Scope;
  registry: PluginRegistry<CLIAgentPluginProvider>;
  exec: IExecutionContext;
  dependencies: HostDependencyResolver;
  fs: PluginFs;
  env: EnvSource;
  homeDir: string;
  platform?: Platform;
};

export type AgentHostError =
  | SpawnContextError
  | { type: 'capability-unsupported'; providerId: string; capability: string }
  | { type: 'invalid-state'; message: string };

export type AgentHostLoginCommand = {
  command: string;
  args: string[];
  env: Record<string, string>;
};

export type AgentHostAcpSpawn = AcpSpawnResult & {
  env: Record<string, string>;
  cwd: string;
};

export class AgentPluginHost {
  readonly dependencies: HostDependencyResolver;

  private readonly scope: Scope;
  private readonly registry: PluginRegistry<CLIAgentPluginProvider>;
  private readonly spawnContext: SpawnContextResolver;
  private readonly checkAuthStatusOnce: (
    providerId: string
  ) => Promise<Result<AgentAuthStatus, AgentHostError>>;

  constructor(private readonly deps: AgentHostDeps) {
    this.scope = deps.scope.child('agent-host');
    this.registry = deps.registry;
    this.dependencies = deps.dependencies;
    this.scope.use(deps.exec);
    this.spawnContext = createSpawnContextResolver({
      resolveCli: (providerId) => this.resolveCli(providerId),
      hasProvider: (providerId) => this.registry.get(providerId) !== undefined,
      env: deps.env,
      homeDir: deps.homeDir,
      includeShellVar: true,
    });
    this.scope.add(() => this.invalidateSpawnContext());
    const checkAuthStatusOnce = compose(
      async (providerId: string, _context: { signal?: AbortSignal }) =>
        await this.checkAuthStatusUncached(providerId),
      [deduplicate({ key: (providerId) => providerId })]
    );
    this.checkAuthStatusOnce = (providerId) => checkAuthStatusOnce(providerId, {});
  }

  get fs(): PluginFs {
    return this.deps.fs;
  }

  get homeDir(): string {
    return this.deps.homeDir;
  }

  async configRootContext(): Promise<ConfigRootContext> {
    return {
      env: buildAllowlistedAgentEnv(await this.deps.env(), {
        homeDir: this.deps.homeDir,
        includeShellVar: true,
      }),
      homeDir: this.deps.homeDir,
      platform: this.deps.platform ?? currentPlatform(),
    };
  }

  get(providerId: string): CLIAgentPluginProvider | undefined {
    return this.registry.get(providerId);
  }

  getAll(): CLIAgentPluginProvider[] {
    return this.registry.getAll();
  }

  resolveAcp(providerId: string): ResolvedAcpProvider | null {
    const plugin = this.registry.get(providerId);
    if (!plugin || plugin.capabilities.acp.kind !== 'supported' || !plugin.behavior.acp) {
      return null;
    }

    return { behavior: plugin.behavior.acp };
  }

  resolveAuthProvider(providerId: string): ResolvedAuthProvider | null {
    const plugin = this.registry.get(providerId);
    if (!plugin) return null;

    return {
      name: plugin.metadata.name,
      auth: plugin.capabilities.auth,
      behavior: plugin.behavior.auth,
    };
  }

  resolveTuiProvider(providerId: string): ResolvedTuiProvider | null {
    const plugin = this.registry.get(providerId);
    const prompt = plugin?.behavior.prompt;
    if (!plugin || !prompt) return null;

    return {
      name: plugin.metadata.name,
      prompt: plugin.capabilities.prompt,
      hooks: plugin.capabilities.hooks,
      buildCommand: prompt.buildCommand,
      parseHookEvent: plugin.behavior.hooks?.parseHookEvent,
      validateSessionId: plugin.behavior.sessions?.validateSessionId,
    };
  }

  resolveSpawnContext(providerId: string): Promise<Result<SpawnContext, SpawnContextError>> {
    return this.spawnContext.resolve(providerId);
  }

  invalidateSpawnContext(providerId?: string): void {
    this.spawnContext.invalidate(providerId);
  }

  dispose(): Promise<void> {
    return this.scope.dispose();
  }

  checkAuthStatus(providerId: string): Promise<Result<AgentAuthStatus, AgentHostError>> {
    return this.checkAuthStatusOnce(providerId);
  }

  async buildLoginCommand(
    providerId: string,
    methodId: string
  ): Promise<Result<AgentHostLoginCommand, AgentHostError>> {
    const provider = this.resolveAuthProvider(providerId);
    if (!provider) return err({ type: 'unknown-provider', providerId });

    const spawnContext = await this.resolveSpawnContext(providerId);
    if (!spawnContext.success) return err(spawnContext.error);
    const env = { ...spawnContext.data.agentEnv };

    if (provider.auth.kind === 'none') {
      if (methodId !== 'cli-login') {
        return err({
          type: 'invalid-state',
          message: `Auth method '${methodId}' was not found for provider '${providerId}'`,
        });
      }
      return ok({ command: spawnContext.data.cli, args: [], env });
    }

    const method = provider.auth.methods.find((candidate) => candidate.id === methodId);
    if (!method) {
      return err({
        type: 'invalid-state',
        message: `Auth method '${methodId}' was not found for provider '${providerId}'`,
      });
    }
    if (method.kind !== 'cli-login') {
      return err({
        type: 'invalid-state',
        message: `Auth method '${methodId}' is not a CLI login method`,
      });
    }

    const override = provider.behavior?.buildLoginCommand?.(
      { cli: spawnContext.data.cli },
      methodId
    );
    return ok({
      command: override?.command ?? spawnContext.data.cli,
      args: override?.args ?? method.args,
      env,
    });
  }

  async readMcpServers(
    providerId: string
  ): Promise<Result<McpServerRegistration[], AgentHostError>> {
    const behavior = this.resolveMcpBehavior(providerId);
    if (!behavior.success) return behavior;
    return ok(await behavior.data.readServers(this.fs));
  }

  async writeMcpServers(
    providerId: string,
    servers: McpServerRegistration[]
  ): Promise<Result<void, AgentHostError>> {
    const behavior = this.resolveMcpBehavior(providerId);
    if (!behavior.success) return behavior;
    await behavior.data.writeServers(this.fs, servers);
    return ok();
  }

  async removeMcpServer(providerId: string, name: string): Promise<Result<void, AgentHostError>> {
    const behavior = this.resolveMcpBehavior(providerId);
    if (!behavior.success) return behavior;
    await behavior.data.removeServer(this.fs, name);
    return ok();
  }

  async buildPromptCommand(
    providerId: string,
    ctx: Omit<CommandContext, 'cli'>
  ): Promise<Result<AgentCommand, AgentHostError>> {
    const provider = this.resolveTuiProvider(providerId);
    if (!provider) return err({ type: 'capability-unsupported', providerId, capability: 'prompt' });
    const spawnContext = await this.resolveSpawnContext(providerId);
    if (!spawnContext.success) return err(spawnContext.error);
    const command = provider.buildCommand({ ...ctx, cli: spawnContext.data.cli });
    return ok({
      ...command,
      env: { ...spawnContext.data.agentEnv, ...command.env },
    });
  }

  async buildAcpSpawn(
    providerId: string,
    ctx: { cwd: string; env?: Record<string, string> }
  ): Promise<Result<AgentHostAcpSpawn, AgentHostError>> {
    const provider = this.resolveAcp(providerId);
    if (!provider) return err({ type: 'capability-unsupported', providerId, capability: 'acp' });
    const spawnContext = await this.resolveSpawnContext(providerId);
    if (!spawnContext.success) return err(spawnContext.error);
    const spawn = provider.behavior.buildSpawn({
      cwd: ctx.cwd,
      env: spawnContext.data.agentEnv,
      cli: spawnContext.data.cli,
    });
    return ok({
      ...spawn,
      // User-configured provider env (from Settings) wins over the allowlisted
      // agent env and any plugin defaults, mirroring the PTY path's providerVars.
      env: { ...spawnContext.data.agentEnv, ...spawn.env, ...(ctx.env ?? {}) },
      cwd: ctx.cwd,
    });
  }

  private async resolveCli(providerId: string): Promise<string> {
    if (!this.registry.get(providerId)) {
      throw new Error(`Provider '${providerId}' was not found`);
    }

    const resolved = await this.dependencies.resolve(providerId);
    if (resolved.success) return resolved.data.path;
    throw new Error(`Provider '${providerId}' CLI could not be resolved: ${resolved.error.type}`);
  }

  private async checkAuthStatusUncached(
    providerId: string
  ): Promise<Result<AgentAuthStatus, AgentHostError>> {
    const provider = this.resolveAuthProvider(providerId);
    if (!provider) return err({ type: 'unknown-provider', providerId });
    if (!provider.behavior || provider.auth.kind === 'none') return ok({ kind: 'unknown' });

    const spawnContext = await this.resolveSpawnContext(providerId);
    if (!spawnContext.success) return err(spawnContext.error);

    return ok(
      await provider.behavior.checkStatus({
        cli: spawnContext.data.cli,
        exec: (command, args, opts) => this.deps.exec.exec(command, args, opts),
        fs: this.fs,
        env: { ...spawnContext.data.agentEnv },
      })
    );
  }

  private resolveMcpBehavior(
    providerId: string
  ): Result<NonNullable<CLIAgentPluginProvider['behavior']['mcp']>, AgentHostError> {
    const provider = this.registry.get(providerId);
    if (!provider) return err({ type: 'unknown-provider', providerId });
    if (provider.capabilities.mcp.kind !== 'supported' || !provider.behavior.mcp) {
      return err({ type: 'capability-unsupported', providerId, capability: 'mcp' });
    }
    return ok(provider.behavior.mcp);
  }
}

function currentPlatform(): Platform {
  if (process.platform === 'darwin') return 'macos';
  if (process.platform === 'win32') return 'windows';
  return 'linux';
}
