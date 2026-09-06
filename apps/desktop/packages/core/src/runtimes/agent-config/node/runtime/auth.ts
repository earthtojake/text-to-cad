import { randomUUID } from 'node:crypto';
import { err, ok, type PendingLease, type Result } from '@emdash/shared';
import {
  createAsyncCache,
  createResourceCache,
  type AsyncCache,
  type ResourceCache,
  type Scope,
} from '@emdash/shared/concurrency';
import type { LiveLogSource } from '@emdash/wire/live';
import type { AgentConfigAuthError, AuthStatusModelState } from '#runtimes/agent-config/api';
import type { AgentAuthStatus, AgentHostError } from '#services/agent-plugins/api/plugins';
import { PtyRegistry, type PtyExitInfo, type PtySession } from '#services/pty/api';
import type { AgentInstallManager } from './install';
import type { AgentConfigRuntimeDeps } from './types';

const CACHE_TTL_MS = 15 * 60 * 1000;
const DEFAULT_COLS = 120;
const DEFAULT_ROWS = 30;
const URL_PATTERN = /https?:\/\/[^\s"'<>]+/i;

export type LoginDimensions = {
  cols: number;
  rows: number;
};

type LoginKey = {
  providerId: string;
  methodId: string;
  generation: string;
  dimensions?: LoginDimensions;
};

type LoginSession = {
  providerId: string;
  generation: string;
  pty: PtySession;
  seenUrls: Set<string>;
};

type LoginLease = {
  generation: string;
  key: LoginKey;
  lease: PendingLease<LoginSession>;
};

export class AgentAuthManager {
  private readonly scope: Scope;
  private readonly statusCache: AsyncCache<string, AgentAuthStatus>;
  private readonly statusGenerations = new Map<string, number>();
  private readonly ptys: PtyRegistry;
  private readonly loginSource: ResourceCache<LoginKey, LoginSession>;
  private readonly loginLeases = new Map<string, LoginLease>();

  constructor(
    private readonly deps: AgentConfigRuntimeDeps,
    private readonly install: AgentInstallManager
  ) {
    this.scope = deps.scope.child('auth');
    this.ptys = new PtyRegistry(deps.ptySpawner);
    this.loginSource = createResourceCache<LoginKey, LoginSession>({
      key: loginKeyId,
      scope: this.scope,
      label: 'login-source',
      create: (key, scope) => this.createLoginSession(key, scope),
      onError: (error, keyId) => {
        deps.logger.warn('AgentAuthManager: login PTY creation failed', {
          key: keyId,
          error: errorMessage(error),
        });
      },
    });
    this.statusCache = createAsyncCache({
      key: (providerId: string) => providerId,
      scope: this.scope,
      label: 'auth-status',
      ttlMs: CACHE_TTL_MS,
      load: (providerId) => this.probeAndPublish(providerId),
      onError: (error, providerId) => {
        deps.logger.warn('AgentAuthManager: status probe failed', {
          providerId,
          error: errorMessage(error),
        });
      },
    });
    this.scope.add(() => {
      this.loginLeases.clear();
      this.statusGenerations.clear();
    });
  }

  async getStatus(
    providerId: string,
    options: { refresh?: boolean } = {}
  ): Promise<AgentAuthStatus> {
    return options.refresh
      ? this.statusCache.refresh(providerId)
      : this.statusCache.get(providerId);
  }

  markUnauthenticated(providerId: string, message?: string): AgentAuthStatus {
    const status: AgentAuthStatus = { kind: 'unauthenticated', message };
    this.nextStatusGeneration(providerId);
    this.updateStatus(providerId, status);
    return status;
  }

  async refreshAuthStatus(
    providerId: string
  ): Promise<Result<AgentAuthStatus, AgentConfigAuthError>> {
    if (!this.hasProvider(providerId)) return err({ type: 'unknown-provider', providerId });
    return ok(await this.getStatus(providerId, { refresh: true }));
  }

  async startLogin(
    providerId: string,
    methodId: string,
    dimensions?: LoginDimensions
  ): Promise<Result<void, AgentConfigAuthError>> {
    if (!this.hasProvider(providerId)) return err({ type: 'unknown-provider', providerId });
    await this.releaseLogin(providerId, undefined, { force: true });
    const generation = randomUUID();
    const key = { providerId, methodId, generation, dimensions };
    const lease = this.loginSource.acquire(key);
    this.loginLeases.set(providerId, { generation, key, lease });
    try {
      await lease.ready();
      if (!this.isCurrentLogin(providerId, generation)) {
        return err({ type: 'invalid-state', message: 'Login was superseded while starting' });
      }
      return ok();
    } catch (error) {
      if (this.isCurrentLogin(providerId, generation)) this.loginLeases.delete(providerId);
      await lease.release();
      return err({ type: 'invalid-state', message: errorMessage(error) });
    }
  }

  async cancelLogin(providerId: string): Promise<Result<void, AgentConfigAuthError>> {
    if (!this.hasProvider(providerId)) return err({ type: 'unknown-provider', providerId });
    await this.releaseLogin(providerId, undefined, { force: true });
    this.publish(providerId, (current) => ({ ...current, login: null }));
    return ok();
  }

  sendLoginInput(providerId: string, data: string): Result<void, AgentConfigAuthError> {
    if (!this.hasProvider(providerId)) return err({ type: 'unknown-provider', providerId });
    const session = this.currentLogin(providerId);
    if (!session) return noLogin(providerId);
    session.pty.write(data);
    return ok();
  }

  resizeLogin(providerId: string, cols: number, rows: number): Result<void, AgentConfigAuthError> {
    if (!this.hasProvider(providerId)) return err({ type: 'unknown-provider', providerId });
    const session = this.currentLogin(providerId);
    if (!session) return noLogin(providerId);
    session.pty.resize(cols, rows);
    return ok();
  }

  markUrlHandled(providerId: string, urlId: string): Result<void, AgentConfigAuthError> {
    if (!this.hasProvider(providerId)) return err({ type: 'unknown-provider', providerId });
    this.publish(providerId, (current) => {
      if (current.login?.pendingUrl?.id !== urlId) return current;
      return {
        ...current,
        login: {
          ...current.login,
          pendingUrl: null,
        },
      };
    });
    return ok();
  }

  loginOutput(providerId: string): LiveLogSource | null {
    return this.currentLogin(providerId)?.pty.output ?? null;
  }

  dispose(): Promise<void> {
    return this.scope.dispose();
  }

  private async createLoginSession(key: LoginKey, scope: Scope): Promise<LoginSession> {
    const { providerId, methodId, generation, dimensions } = key;
    const loginCommand = await this.deps.agentHost.buildLoginCommand(providerId, methodId);
    if (!loginCommand.success) throw new Error(agentConfigAuthErrorMessage(loginCommand.error));
    const { command, args, env } = loginCommand.data;
    if (!this.isCurrentLogin(providerId, generation)) {
      throw new Error('Login was superseded while resolving the login command');
    }
    const startedAt = Date.now();
    const seenUrls = new Set<string>();
    this.publish(providerId, (current) => ({
      ...current,
      login: {
        methodId,
        startedAt,
        pendingUrl: null,
        exit: null,
      },
    }));

    const pty = await this.ptys.create(
      providerId,
      {
        command,
        args,
        cwd: this.deps.agentHost.homeDir,
        env,
        cols: dimensions?.cols ?? DEFAULT_COLS,
        rows: dimensions?.rows ?? DEFAULT_ROWS,
      },
      {
        replaceExisting: false,
        onData: (chunk) => this.detectUrl(providerId, generation, seenUrls, chunk),
        onExit: (info) => {
          void this.handleLoginExit(providerId, generation, info);
        },
      }
    );
    scope.add(() => {
      if (this.ptys.get(providerId) === pty) this.ptys.dispose(providerId);
    });
    return { providerId, generation, pty, seenUrls };
  }

  private async handleLoginExit(
    providerId: string,
    generation: string,
    info: PtyExitInfo
  ): Promise<void> {
    if (!this.isCurrentLogin(providerId, generation)) return;
    this.publishLoginExit(providerId, generation, info);
    await this.releaseLogin(providerId, generation);
    if (this.scope.disposed) return;
    await this.getStatus(providerId, { refresh: true }).catch((error) => {
      this.deps.logger.warn('AgentAuthManager: failed to refresh auth after login exit', {
        providerId,
        error: error instanceof Error ? error.message : String(error),
      });
    });
  }

  private async releaseLogin(
    providerId: string,
    generation?: string,
    options: { force?: boolean } = {}
  ): Promise<void> {
    const entry = this.loginLeases.get(providerId);
    if (entry) {
      if (generation && entry.generation !== generation) return;
      this.loginLeases.delete(providerId);
      if (options.force) await this.loginSource.invalidate(entry.key);
      await entry.lease.release();
      return;
    }
  }

  private async probeAndPublish(providerId: string): Promise<AgentAuthStatus> {
    const generation = this.nextStatusGeneration(providerId);
    const status = await this.probe(providerId);
    if (!this.scope.disposed && this.statusGenerations.get(providerId) === generation) {
      this.publishStatus(providerId, status);
    }
    return status;
  }

  private async probe(providerId: string): Promise<AgentAuthStatus> {
    try {
      const status = await this.deps.agentHost.checkAuthStatus(providerId);
      if (!status.success) {
        this.deps.logger.warn('AgentAuthManager: spawn context resolution failed', {
          providerId,
          error: agentConfigAuthErrorMessage(status.error),
        });
        return { kind: 'unknown' };
      }
      return status.data;
    } catch (error) {
      this.deps.logger.warn('AgentAuthManager: status probe failed', {
        providerId,
        error: errorMessage(error),
      });
      return { kind: 'unknown' };
    }
  }

  private detectUrl(
    providerId: string,
    generation: string,
    seenUrls: Set<string>,
    chunk: string
  ): void {
    if (!this.isCurrentLogin(providerId, generation)) return;
    const match = URL_PATTERN.exec(chunk);
    if (!match) return;

    const url = stripTrailingUrlPunctuation(match[0]);
    if (seenUrls.has(url)) return;
    seenUrls.add(url);

    this.publish(providerId, (current) => {
      if (!current.login || current.login.pendingUrl) return current;
      return {
        ...current,
        login: {
          ...current.login,
          pendingUrl: { id: randomUUID(), url },
        },
      };
    });
  }

  private publishLoginExit(providerId: string, generation: string, exit: PtyExitInfo): void {
    if (!this.isCurrentLogin(providerId, generation)) return;
    this.publish(providerId, (current) => {
      if (!current.login) return current;
      return {
        ...current,
        login: {
          ...current.login,
          exit,
        },
      };
    });
  }

  private updateStatus(providerId: string, status: AgentAuthStatus): void {
    this.statusCache.set(providerId, status);
    this.publishStatus(providerId, status);
  }

  private publishStatus(providerId: string, status: AgentAuthStatus): void {
    this.publish(providerId, (current) => ({
      status,
      login: status.kind === 'authenticated' ? null : current.login,
    }));
  }

  private publish(
    providerId: string,
    update: (current: AuthStatusModelState) => AuthStatusModelState
  ): void {
    if (this.scope.disposed) return;
    const current = this.install.getAuth(providerId);
    this.install.updateAuth(providerId, update(current));
  }

  private hasProvider(providerId: string): boolean {
    return this.deps.agentHost.get(providerId) !== undefined;
  }

  private currentLogin(providerId: string): LoginSession | null {
    const active = this.loginLeases.get(providerId);
    const session = active ? this.loginSource.peek(active.key) : undefined;
    if (!session || !this.isCurrentLogin(providerId, session.generation)) return null;
    return session;
  }

  private isCurrentLogin(providerId: string, generation: string): boolean {
    return this.loginLeases.get(providerId)?.generation === generation;
  }

  private nextStatusGeneration(providerId: string): number {
    const next = (this.statusGenerations.get(providerId) ?? 0) + 1;
    this.statusGenerations.set(providerId, next);
    return next;
  }
}

function stripTrailingUrlPunctuation(url: string): string {
  return url.replace(/[),.;\]]+$/u, '');
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function loginKeyId(key: LoginKey): string {
  return `${key.providerId}:${key.methodId}:${key.generation}`;
}

function agentConfigAuthErrorMessage(error: AgentConfigAuthError | AgentHostError): string {
  return 'message' in error ? error.message : error.type;
}

function noLogin(providerId: string): Result<void, AgentConfigAuthError> {
  return err({
    type: 'invalid-state',
    message: `No login PTY is active for provider '${providerId}'`,
  });
}
