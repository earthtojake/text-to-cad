import type { Result } from '@emdash/shared';
import { err, ok } from '@emdash/shared';
import type { Logger } from '@emdash/shared/logger';
import { afterEach, describe, expect, it } from 'vitest';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import type { Resolved } from '@core/primitives/project-settings/api';
import { GitCredentialServer } from './git-credential-server';

const SECRET_TOKEN = 'ghp_SECRET_TOKEN_MATERIAL_do_not_leak';

const account: GitHubAccountSummary = {
  accountId: 'account-1',
  host: 'github.com',
  login: 'octocat',
  avatarUrl: 'https://example.invalid/a.png',
  credentialSource: 'emdash_oauth',
  isDefault: true,
};

function makeHarness(
  options: {
    resolution?: Resolved<GitHubAccountSummary | null>;
    accounts?: GitHubAccountSummary[];
    tokenResult?: Result<string, unknown>;
  } = {}
) {
  const logLines: string[] = [];
  const record = (message: unknown, meta?: unknown) => {
    logLines.push(`${String(message)} ${JSON.stringify(meta ?? {})}`);
  };
  const logger = {
    info: record,
    warn: record,
    error: record,
    debug: record,
  } as unknown as Logger;
  const server = new GitCredentialServer({
    resolveProjectGitHubAccount: async () =>
      options.resolution ?? { value: account, provenance: { kind: 'set' } },
    listAccounts: async () => options.accounts ?? [account],
    getToken: async () => options.tokenResult ?? ok(SECRET_TOKEN),
    logger,
  });
  return { server, logLines };
}

async function requestCredential(
  channel: { port: number; nonce: string },
  body: string,
  nonceOverride?: string
): Promise<{ status: number; text: string }> {
  const response = await fetch(`http://127.0.0.1:${channel.port}/git-credential/get`, {
    method: 'POST',
    headers: { 'X-Emdash-Token': nonceOverride ?? channel.nonce },
    body,
  });
  return { status: response.status, text: await response.text() };
}

describe('GitCredentialServer', () => {
  const servers: GitCredentialServer[] = [];
  afterEach(() => {
    for (const server of servers.splice(0)) server.stop();
  });

  function track(harness: ReturnType<typeof makeHarness>) {
    servers.push(harness.server);
    return harness;
  }

  it('answers a project-session get with the effective account credentials', async () => {
    const { server } = track(makeHarness());
    const channel = await server.mintSession({ kind: 'project', projectId: 'project-1' });

    const result = await requestCredential(channel, 'protocol=https\nhost=github.com\n');
    expect(result.status).toBe(200);
    expect(result.text).toBe(`username=octocat\npassword=${SECRET_TOKEN}\n`);
    // The channel handle itself carries no token material.
    expect(JSON.stringify(channel)).not.toContain(SECRET_TOKEN);
  });

  it('rejects unknown and revoked nonces', async () => {
    const { server } = track(makeHarness());
    const channel = await server.mintSession({ kind: 'project', projectId: 'project-1' });

    const bad = await requestCredential(channel, 'protocol=https\nhost=github.com\n', 'wrong');
    expect(bad.status).toBe(403);
    expect(bad.text).toBe('');

    server.revokeSession(channel.nonce);
    const revoked = await requestCredential(channel, 'protocol=https\nhost=github.com\n');
    expect(revoked.status).toBe(403);
  });

  it('denies non-https requests and host mismatches', async () => {
    const { server } = track(makeHarness());
    const channel = await server.mintSession({ kind: 'project', projectId: 'project-1' });

    expect((await requestCredential(channel, 'protocol=http\nhost=github.com\n')).status).toBe(404);
    expect((await requestCredential(channel, 'protocol=https\nhost=evil.example\n')).status).toBe(
      404
    );
  });

  it('fails closed when the project account resolution yields no account', async () => {
    const { server } = track(
      makeHarness({ resolution: { value: null, provenance: { kind: 'unresolvable' } } })
    );
    const channel = await server.mintSession({ kind: 'project', projectId: 'project-1' });

    const result = await requestCredential(channel, 'protocol=https\nhost=github.com\n');
    expect(result.status).toBe(404);
    expect(result.text).toBe('');
  });

  it('fails closed when token resolution errors (stale pin)', async () => {
    const { server } = track(makeHarness({ tokenResult: err({ type: 'host-mismatch' }) }));
    const channel = await server.mintSession({ kind: 'project', projectId: 'project-1' });

    const result = await requestCredential(channel, 'protocol=https\nhost=github.com\n');
    expect(result.status).toBe(404);
  });

  it('answers host sessions with the default account for that host only', async () => {
    const { server } = track(makeHarness());
    const channel = await server.mintSession({ kind: 'host', host: 'github.com' });

    const match = await requestCredential(channel, 'protocol=https\nhost=github.com\n');
    expect(match.status).toBe(200);
    const mismatch = await requestCredential(channel, 'protocol=https\nhost=ghe.example\n');
    expect(mismatch.status).toBe(404);
  });

  it('never writes token material to its logs', async () => {
    const harness = track(makeHarness());
    const channel = await harness.server.mintSession({ kind: 'project', projectId: 'project-1' });
    await requestCredential(channel, 'protocol=https\nhost=github.com\n');
    await requestCredential(channel, 'protocol=https\nhost=evil.example\n');
    await requestCredential(channel, 'protocol=https\nhost=github.com\n', 'wrong');

    expect(harness.logLines.join('\n')).not.toContain(SECRET_TOKEN);
  });
});
