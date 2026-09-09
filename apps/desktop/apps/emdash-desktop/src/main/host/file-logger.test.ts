import { mkdtemp, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { redactAll } from '@emdash/shared/logger';
import { describe, expect, it, vi } from 'vitest';
import { flushLogWrites, isDiskFullError, writeRendererLogEntry } from './file-logger';

vi.mock('electron', () => ({
  app: {
    exit: vi.fn(),
    getPath: vi.fn(() => '/tmp/emdash-test'),
    setAppLogsPath: vi.fn(),
  },
}));

describe('file transport output', () => {
  it('writes redacted lines by default, with no explicit redact wiring', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'emdash-file-logger-test-'));
    const logFile = join(dir, 'emdash.log');
    process.env.EMDASH_LOG_FILE = logFile;

    const token = `ghp_${'a'.repeat(36)}`;
    writeRendererLogEntry({
      level: 'info',
      source: 'renderer',
      input: [`token is ${token}`],
    });
    await flushLogWrites();

    const written = await readFile(logFile, 'utf8');
    expect(written).not.toContain(token);
    expect(written).toContain('[REDACTED_GITHUB_TOKEN]');
  });
});

describe('redactAll', () => {
  it('redacts common secrets in free-form text', () => {
    const redacted = redactAll(
      [
        'authorization: Bearer abc123',
        'api_key=super-secret-key',
        'token: ghp_123456',
        'password=hunter2',
        'sk-abcdefghijklmnopqrstuvwxyz123456',
      ].join('\n')
    );

    expect(redacted).toContain('authorization: [REDACTED]');
    expect(redacted).toContain('api_key=[REDACTED]');
    expect(redacted).toContain('token: [REDACTED]');
    expect(redacted).toContain('password=[REDACTED]');
    expect(redacted).toContain('[REDACTED_OPENAI_KEY]');
  });

  it('redacts secrets embedded in JSON-quoted values', () => {
    const redacted = redactAll(
      JSON.stringify({
        password: 'hunter2',
        api_key: 'super-secret-key',
        authorization: 'Bearer xyz',
        access_token: 'abc',
      })
    );

    expect(redacted).not.toContain('hunter2');
    expect(redacted).not.toContain('super-secret-key');
    expect(redacted).not.toContain('Bearer xyz');
    expect(redacted).not.toContain('"abc"');
    expect(redacted).toContain('[REDACTED]');
  });

  it('redacts secrets embedded in escaped JSON-in-JSON strings', () => {
    const inner = JSON.stringify({ password: 'hunter2' });
    const outer = JSON.stringify({ message: inner });

    const redacted = redactAll(outer);

    expect(redacted).not.toContain('hunter2');
  });

  it('redacts vendor-specific tokens', () => {
    const redacted = redactAll(
      [
        'ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'glpat-aaaaaaaaaaaaaaaaaaaa',
        'AKIAABCDEFGHIJKLMNOP',
        'sk_live_aaaaaaaaaaaaaaaaaaaa',
        'sk-ant-aaaaaaaaaaaaaaaaaaaaaaaa',
        'xoxb-redacted-example-token',
        'eyJabcdefgh.eyJabcdefgh.signaturebits',
        'npm_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      ].join('\n')
    );

    expect(redacted).toContain('[REDACTED_GITHUB_TOKEN]');
    expect(redacted).toContain('[REDACTED_GITLAB_TOKEN]');
    expect(redacted).toContain('[REDACTED_AWS_KEY]');
    expect(redacted).toContain('[REDACTED_STRIPE_KEY]');
    expect(redacted).toContain('[REDACTED_ANTHROPIC_KEY]');
    expect(redacted).toContain('[REDACTED_SLACK_TOKEN]');
    expect(redacted).toContain('[REDACTED_JWT]');
    expect(redacted).toContain('[REDACTED_NPM_TOKEN]');
  });

  it('redacts PEM private-key blocks', () => {
    const pem = [
      '-----BEGIN RSA PRIVATE KEY-----',
      'MIIEpAIBAAKCAQEAxyz...',
      '-----END RSA PRIVATE KEY-----',
    ].join('\n');

    expect(redactAll(pem)).toBe('[REDACTED_PEM_BLOCK]');
  });

  it('redacts credentials in non-HTTPS DSNs', () => {
    const redacted = redactAll(
      [
        'postgres://admin:s3cret@db.internal/app',
        'mongodb://user:pass@cluster.example.com',
        'redis://default:topsecret@cache.local:6379',
      ].join('\n')
    );

    expect(redacted).toContain('postgres://[REDACTED_CREDENTIALS]@');
    expect(redacted).toContain('mongodb://[REDACTED_CREDENTIALS]@');
    expect(redacted).toContain('redis://[REDACTED_CREDENTIALS]@');
    expect(redacted).not.toContain('s3cret');
    expect(redacted).not.toContain('topsecret');
  });

  it('redacts common PII while keeping useful path shape', () => {
    const redacted = redactAll(
      [
        'email person@example.com',
        'mac /Users/alice/projects/emdash',
        'linux /home/bob/work/repo',
        'win C:\\Users\\carol\\repo',
        'ipv4 192.168.1.25',
        'ipv6 2001:0db8:85a3:0000:0000:8a2e:0370:7334',
        'macaddr aa:bb:cc:dd:ee:ff',
        'remote git@github.com',
        'url https://alice:secret@example.com/repo',
      ].join('\n')
    );

    expect(redacted).toContain('[REDACTED_EMAIL]');
    expect(redacted).toContain('/Users/[REDACTED_USER]/projects/emdash');
    expect(redacted).toContain('/home/[REDACTED_USER]/work/repo');
    expect(redacted).toContain('C:\\Users\\[REDACTED_USER]\\repo');
    expect(redacted).toContain('ipv4 [REDACTED_IP]');
    expect(redacted).toContain('ipv6 [REDACTED_IP]');
    expect(redacted).toContain('macaddr [REDACTED_MAC]');
    expect(redacted).toContain('git@[REDACTED_HOST]');
    expect(redacted).toContain('https://[REDACTED_CREDENTIALS]@example.com/repo');
  });
});

describe('isDiskFullError', () => {
  it('recognises the Node errors a full or quota-limited disk raises', () => {
    expect(isDiskFullError(Object.assign(new Error('write'), { code: 'ENOSPC' }))).toBe(true);
    expect(isDiskFullError({ code: 'EDQUOT' })).toBe(true);
  });

  it('leaves every other rejection reason fatal', () => {
    expect(isDiskFullError(new Error('boom'))).toBe(false);
    expect(isDiskFullError(Object.assign(new Error('io'), { code: 'EIO' }))).toBe(false);
    expect(isDiskFullError('ENOSPC')).toBe(false);
    expect(isDiskFullError(null)).toBe(false);
  });
});
