// Every setting the server reads, from the environment, checked once at start-up.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import pkg from '../package.json' with { type: 'json' };

export type Env = Record<string, string | undefined>;

export interface Limits {
  buildTimeoutSeconds: number;
  buildVcpus: number;
  jobTimeoutSeconds: number;
  jobVcpus: number;
  memoryGbPerVcpu: number;
  maxFiles: number;
  maxInputBytes: number;
  maxOutputBytes: number;
  maxOutputFiles: number;
  maxCodeBytes: number;
  userDailyVcpuSeconds: number;
  dailyBudgetUsd: number;
  cpuHourUsd: number;
  gbHourUsd: number;
  /** The least time a job is started with; less than this left today refuses it. */
  minJobSeconds: number;
  /** How long a tool call or `?wait=` waits for a running build or job. */
  toolWaitSeconds: number;
  /** How long past its timeout a running job is presumed dead by the sweeper. */
  staleGraceSeconds: number;
}

export interface Config {
  production: boolean;
  publicUrl: string;
  port: number;
  host: string;
  cadgenVersion: string;
  auth: {
    mode: 'dev' | 'oauth';
    issuer?: string;
    jwksUrl?: string;
    audiences: string[];
    clientId?: string;
    clientSecret?: string;
    scopes: string;
    sessionSecret: string;
  };
  db: { url?: string; pgliteDir?: string };
  storage:
    | { kind: 'fs'; dir: string }
    | {
        kind: 'r2';
        endpoint: string;
        bucket: string;
        accessKeyId: string;
        secretAccessKey: string;
        publicBaseUrl: string;
      };
  sandbox:
    | { kind: 'local'; python: string; runner: string; allowInProduction: boolean; jobsDir?: string }
    | {
        kind: 'vercel';
        snapshotId: string;
        python: string;
        runner: string;
        jobRoot: string;
        credentials?: { teamId: string; projectId: string; token: string };
      };
  limits: Limits;
  distDir: string;
  cronSecret?: string;
}

const APP_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const REPO_DIR = path.resolve(APP_DIR, '../..');

class ConfigError extends Error {}

function number(env: Env, name: string, fallback: number, { min = 0 }: { min?: number } = {}): number {
  const raw = env[name];
  if (raw === undefined || raw === '') return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value) || value < min) throw new ConfigError(`${name} must be a number >= ${min}, not ${JSON.stringify(raw)}`);
  return value;
}

function required(env: Env, name: string, why: string): string {
  const value = env[name]?.trim();
  if (!value) throw new ConfigError(`${name} is required ${why}`);
  return value;
}

const trimSlash = (url: string) => url.replace(/\/+$/, '');

export function loadConfig(env: Env = process.env): Config {
  const production = env.NODE_ENV === 'production';
  const port = number(env, 'PORT', 8787, { min: 0 });
  const vercelUrl = env.VERCEL_PROJECT_PRODUCTION_URL || env.VERCEL_URL;
  const publicUrl = trimSlash(env.CLOUD_PUBLIC_URL || (vercelUrl ? `https://${vercelUrl}` : `http://localhost:${port}`));
  if (!/^https?:\/\/[^/]+$/.test(publicUrl)) throw new ConfigError(`CLOUD_PUBLIC_URL must be an origin like https://cad.example.com, not ${publicUrl}`);

  const authMode = env.CLOUD_AUTH === 'dev' ? 'dev' : 'oauth';
  if (authMode === 'dev' && production) {
    throw new ConfigError('CLOUD_AUTH=dev signs everyone in as one user; it is refused when NODE_ENV=production');
  }
  const sessionSecret = env.SESSION_SECRET || (authMode === 'dev' || !production ? 'development-only-session-secret-not-for-production' : '');
  if (sessionSecret.length < 32) throw new ConfigError('SESSION_SECRET must be at least 32 characters (it signs sign-in cookies)');
  const issuer = env.AUTH_ISSUER ? trimSlash(env.AUTH_ISSUER) : undefined;
  if (authMode === 'oauth' && production && !issuer) throw new ConfigError('AUTH_ISSUER is required unless CLOUD_AUTH=dev');
  const audiences = (env.AUTH_AUDIENCE ? env.AUTH_AUDIENCE.split(',').map((item) => item.trim()).filter(Boolean) : [])
    .concat([`${publicUrl}/mcp`, publicUrl]);

  const storageKind = env.CLOUD_STORAGE || (env.R2_BUCKET ? 'r2' : 'fs');
  let storage: Config['storage'];
  if (storageKind === 'r2') {
    const accountId = env.R2_ACCOUNT_ID;
    const endpoint = trimSlash(env.R2_ENDPOINT || (accountId ? `https://${accountId}.r2.cloudflarestorage.com` : ''));
    if (!endpoint) throw new ConfigError('R2_ENDPOINT or R2_ACCOUNT_ID is required when CLOUD_STORAGE=r2');
    storage = {
      kind: 'r2',
      endpoint,
      bucket: required(env, 'R2_BUCKET', 'when CLOUD_STORAGE=r2'),
      accessKeyId: required(env, 'R2_ACCESS_KEY_ID', 'when CLOUD_STORAGE=r2'),
      secretAccessKey: required(env, 'R2_SECRET_ACCESS_KEY', 'when CLOUD_STORAGE=r2'),
      publicBaseUrl: trimSlash(required(env, 'R2_PUBLIC_BASE_URL', 'when CLOUD_STORAGE=r2 (the public, CORS-enabled bucket domain)')),
    };
  } else if (storageKind === 'fs') {
    storage = { kind: 'fs', dir: path.resolve(env.CLOUD_FS_DIR || path.join(REPO_DIR, 'tmp/cloud/store')) };
  } else {
    throw new ConfigError(`CLOUD_STORAGE must be fs or r2, not ${storageKind}`);
  }

  const sandboxKind = env.CLOUD_SANDBOX || (env.CLOUD_SANDBOX_SNAPSHOT ? 'vercel' : 'local');
  let sandbox: Config['sandbox'];
  if (sandboxKind === 'local') {
    const allowInProduction = env.CLOUD_ALLOW_LOCAL_SANDBOX === '1';
    if (production && !allowInProduction) {
      throw new ConfigError('CLOUD_SANDBOX=local runs uploaded code on this machine without isolation; it is refused when NODE_ENV=production unless CLOUD_ALLOW_LOCAL_SANDBOX=1');
    }
    sandbox = {
      kind: 'local',
      python: env.CLOUD_PYTHON || path.join(REPO_DIR, '.venv/bin/python'),
      runner: path.join(APP_DIR, 'runner/run.py'),
      allowInProduction,
      jobsDir: env.CLOUD_LOCAL_JOBS_DIR || undefined,
    };
  } else if (sandboxKind === 'vercel') {
    const credentials = env.VERCEL_TEAM_ID && env.VERCEL_PROJECT_ID && env.VERCEL_TOKEN
      ? { teamId: env.VERCEL_TEAM_ID, projectId: env.VERCEL_PROJECT_ID, token: env.VERCEL_TOKEN }
      : undefined;
    sandbox = {
      kind: 'vercel',
      snapshotId: required(env, 'CLOUD_SANDBOX_SNAPSHOT', 'when CLOUD_SANDBOX=vercel (print one with scripts/cloud/prepare-sandbox.mjs)'),
      python: env.CLOUD_SANDBOX_PYTHON || '/vercel/sandbox/venv/bin/python',
      runner: env.CLOUD_SANDBOX_RUNNER || '/vercel/sandbox/runner/run.py',
      jobRoot: env.CLOUD_SANDBOX_JOB_DIR || '/vercel/sandbox/job',
      credentials,
    };
  } else {
    throw new ConfigError(`CLOUD_SANDBOX must be local or vercel, not ${sandboxKind}`);
  }

  const limits: Limits = {
    buildTimeoutSeconds: number(env, 'CLOUD_BUILD_TIMEOUT_S', 600, { min: 10 }),
    buildVcpus: number(env, 'CLOUD_BUILD_VCPUS', 2, { min: 1 }),
    jobTimeoutSeconds: number(env, 'CLOUD_JOB_TIMEOUT_S', 180, { min: 10 }),
    jobVcpus: number(env, 'CLOUD_JOB_VCPUS', 2, { min: 1 }),
    memoryGbPerVcpu: number(env, 'CLOUD_MEMORY_GB_PER_VCPU', 2, { min: 0 }),
    maxFiles: number(env, 'CLOUD_MAX_FILES', 400, { min: 1 }),
    maxInputBytes: number(env, 'CLOUD_MAX_INPUT_BYTES', 20 * 1024 * 1024, { min: 1 }),
    maxOutputBytes: number(env, 'CLOUD_MAX_OUTPUT_BYTES', 200 * 1024 * 1024, { min: 1 }),
    maxOutputFiles: number(env, 'CLOUD_MAX_OUTPUT_FILES', 5000, { min: 1 }),
    maxCodeBytes: number(env, 'CLOUD_MAX_CODE_BYTES', 256 * 1024, { min: 1 }),
    userDailyVcpuSeconds: number(env, 'CLOUD_USER_DAILY_VCPU_S', 3600, { min: 0 }),
    dailyBudgetUsd: number(env, 'CLOUD_DAILY_BUDGET_USD', 5, { min: 0 }),
    cpuHourUsd: number(env, 'CLOUD_CPU_HOUR_USD', 0.128, { min: 0 }),
    gbHourUsd: number(env, 'CLOUD_GB_HOUR_USD', 0.0212, { min: 0 }),
    minJobSeconds: number(env, 'CLOUD_MIN_JOB_S', 30, { min: 1 }),
    toolWaitSeconds: number(env, 'CLOUD_TOOL_WAIT_S', 40, { min: 0 }),
    staleGraceSeconds: number(env, 'CLOUD_STALE_GRACE_S', 300, { min: 0 }),
  };

  return {
    production,
    publicUrl,
    port,
    host: env.HOST || '127.0.0.1',
    cadgenVersion: env.CLOUD_CADGEN_VERSION || pkg.version,
    auth: {
      mode: authMode,
      issuer,
      jwksUrl: env.AUTH_JWKS_URL || undefined,
      audiences: [...new Set(audiences)],
      clientId: env.AUTH_CLIENT_ID || undefined,
      clientSecret: env.AUTH_CLIENT_SECRET || undefined,
      scopes: env.AUTH_SCOPES || 'openid profile email',
      sessionSecret,
    },
    db: { url: env.DATABASE_URL || undefined, pgliteDir: env.CLOUD_PGLITE_DIR || undefined },
    storage,
    sandbox,
    limits,
    distDir: path.resolve(env.CLOUD_DIST_DIR || path.join(APP_DIR, 'dist')),
    cronSecret: env.CRON_SECRET || undefined,
  };
}

export { ConfigError };
