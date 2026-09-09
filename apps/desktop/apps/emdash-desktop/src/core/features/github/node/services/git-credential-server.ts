import crypto from 'node:crypto';
import http from 'node:http';
import {
  parseGitCredentialRequest,
  serializeGitCredentialResponse,
  GIT_CREDENTIAL_HELPER_URL_PATH,
  type GitCredentialChannel,
} from '@emdash/core/primitives/git-credentials/api';
import type { Result } from '@emdash/shared';
import type { Logger } from '@emdash/shared/logger';
import type {
  GitCredentialChannelServer,
  GitCredentialSessionTarget,
} from '@core/features/github/api/node/services/git-credentials-service';
import type {
  ProjectGitHubAccountResolver,
  ProjectGitHubAccountResolution,
} from '@core/features/github/api/node/services/project-github-account-resolver';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import { resolveAccountForHost } from '@core/primitives/project-settings/api';
import { normalizeRepositoryHost } from '@core/primitives/repository/api';

/**
 * Loopback credential server behind the emdash git credential helper
 * (spec: github-git-settings §4; secrets spec "first consumer" seam).
 *
 * Sessions carry only `{ port, nonce }` — the token stays desktop-side and is
 * re-resolved on every request through the blessed resolver, so revoking an
 * account or repointing a pin takes effect immediately and a broken pin fails
 * closed. The token travels exclusively over this loopback response body to
 * the helper's stdout; it is never logged and never enters an environment.
 */

export type GitCredentialServerDeps = {
  resolveProjectGitHubAccount: ProjectGitHubAccountResolver;
  listAccounts(): Promise<GitHubAccountSummary[]>;
  /** Token access with fail-closed pin checks (GitHubApiAuthService.getToken). */
  getToken(host: string, context: { accountId?: string }): Promise<Result<string, unknown>>;
  logger: Logger;
};

const MAX_BODY_BYTES = 64 * 1024;
/** PTY-session channels live as long as the session; cap to bound the map. */
const MAX_SESSIONS = 512;

export class GitCredentialServer implements GitCredentialChannelServer {
  private server: http.Server | null = null;
  private port = 0;
  private starting: Promise<number> | null = null;
  private readonly sessions = new Map<string, GitCredentialSessionTarget>();

  constructor(private readonly deps: GitCredentialServerDeps) {}

  async mintSession(target: GitCredentialSessionTarget): Promise<GitCredentialChannel> {
    const port = await this.ensureStarted();
    const nonce = crypto.randomBytes(24).toString('hex');
    if (this.sessions.size >= MAX_SESSIONS) {
      const oldest = this.sessions.keys().next().value;
      if (oldest !== undefined) this.sessions.delete(oldest);
    }
    this.sessions.set(nonce, target);
    return { port, nonce };
  }

  revokeSession(nonce: string): void {
    this.sessions.delete(nonce);
  }

  stop(): void {
    this.sessions.clear();
    if (this.server) {
      this.server.close();
      this.server = null;
      this.port = 0;
    }
  }

  private ensureStarted(): Promise<number> {
    if (this.server && this.port > 0) return Promise.resolve(this.port);
    if (this.starting) return this.starting;

    const server = http.createServer((req, res) => this.handleRequest(req, res));
    this.server = server;
    this.starting = new Promise<number>((resolve, reject) => {
      server.listen(0, '127.0.0.1', () => {
        const addr = server.address();
        this.port = addr && typeof addr === 'object' ? addr.port : 0;
        this.deps.logger.info('GitCredentialServer: started', { port: this.port });
        resolve(this.port);
      });
      server.on('error', (error) => {
        this.deps.logger.error('GitCredentialServer: failed to start', { error: String(error) });
        this.server = null;
        this.port = 0;
        this.starting = null;
        reject(error);
      });
    }).finally(() => {
      this.starting = null;
    });
    return this.starting;
  }

  private handleRequest(req: http.IncomingMessage, res: http.ServerResponse): void {
    if (req.method !== 'POST' || req.url !== GIT_CREDENTIAL_HELPER_URL_PATH) {
      res.writeHead(404);
      res.end();
      return;
    }
    const nonce = String(req.headers['x-emdash-token'] ?? '');
    const target = nonce ? this.sessions.get(nonce) : undefined;
    if (!target) {
      this.deps.logger.warn('GitCredentialServer: rejected request with unknown session nonce');
      res.writeHead(403);
      res.end();
      return;
    }

    let body = '';
    req.on('data', (chunk: Buffer) => {
      body += chunk.toString();
      if (body.length > MAX_BODY_BYTES) req.destroy();
    });
    req.on('end', () => {
      this.respond(target, body, res).catch((error) => {
        // Never include the request body or credentials in logs.
        this.deps.logger.warn('GitCredentialServer: request failed', { error: String(error) });
        res.writeHead(500);
        res.end();
      });
    });
  }

  private async respond(
    target: GitCredentialSessionTarget,
    body: string,
    res: http.ServerResponse
  ): Promise<void> {
    const request = parseGitCredentialRequest(body);
    const requestHost = normalizeRepositoryHost(request.host ?? '');
    if (request.protocol !== 'https' || !requestHost) {
      res.writeHead(404);
      res.end();
      return;
    }

    const account = await this.resolveAccount(target, requestHost);
    if (!account) {
      this.deps.logger.info('GitCredentialServer: no credential for request', {
        targetKind: target.kind,
        host: requestHost,
      });
      res.writeHead(404);
      res.end();
      return;
    }

    // getToken re-runs the fail-closed pin checks (dangling account, host
    // mismatch) so a stale session can never yield another identity.
    const token = await this.deps.getToken(requestHost, { accountId: account.accountId });
    if (!token.success) {
      this.deps.logger.warn('GitCredentialServer: token resolution failed closed', {
        targetKind: target.kind,
        host: requestHost,
        accountId: account.accountId,
      });
      res.writeHead(404);
      res.end();
      return;
    }

    res.writeHead(200, { 'content-type': 'text/plain; charset=utf-8' });
    res.end(serializeGitCredentialResponse({ username: account.login, password: token.data }));
  }

  private async resolveAccount(
    target: GitCredentialSessionTarget,
    requestHost: string
  ): Promise<GitHubAccountSummary | null> {
    if (target.kind === 'host') {
      if (normalizeRepositoryHost(target.host) !== requestHost) return null;
      const inferred = resolveAccountForHost(requestHost, await this.deps.listAccounts());
      return inferred.value;
    }

    const resolution: ProjectGitHubAccountResolution = await this.deps.resolveProjectGitHubAccount(
      target.projectId
    );
    const account = resolution.value;
    if (!account) return null;
    // The helper config is scoped to the account's host; still verify, since
    // the session env could be replayed against other hosts.
    if (normalizeRepositoryHost(account.host) !== requestHost) return null;
    return account;
  }
}
