import type {
  AgentAuthContext,
  AgentAuthStatus,
} from '@emdash/core/services/agent-plugins/api/plugins';
import { authenticatedFromEnv } from '../../helpers/auth';

const AUTH_STATUS_TIMEOUT_MS = 5_000;
const LOGGED_OUT_PATTERN = /not (authenticated|logged in|signed in)|login required|logged out/i;

type ExecErrorWithOutput = {
  code?: unknown;
  stdout?: unknown;
  stderr?: unknown;
  message?: unknown;
};

export async function claudeAuthStatus(ctx: AgentAuthContext): Promise<AgentAuthStatus> {
  const envStatus = authenticatedFromEnv(ctx, ['ANTHROPIC_API_KEY']);
  if (envStatus.kind === 'authenticated') return envStatus;

  try {
    const { stdout } = await ctx.exec(ctx.cli, ['auth', 'status'], {
      timeout: AUTH_STATUS_TIMEOUT_MS,
    });
    return { kind: 'authenticated', account: accountFromAuthStatus(stdout) };
  } catch (error) {
    const output = outputFromExecError(error);
    if (isExitCode(error, 1) && isAuthStatusResponse(output)) {
      return { kind: 'unauthenticated' };
    }
    return { kind: 'unknown' };
  }
}

function isExitCode(error: unknown, code: number): boolean {
  return (
    typeof error === 'object' && error !== null && (error as ExecErrorWithOutput).code === code
  );
}

function isAuthStatusResponse(output: ExecErrorOutput): boolean {
  if (parseAuthStatus(output.stdout)) return true;
  return LOGGED_OUT_PATTERN.test(output.combined);
}

function accountFromAuthStatus(output: string): string | undefined {
  const status = parseAuthStatus(output);
  const oauthAccount = objectValue(status?.oauthAccount);
  return firstString(
    status?.email,
    status?.account,
    status?.accountEmail,
    oauthAccount?.emailAddress,
    oauthAccount?.email
  );
}

function parseAuthStatus(output: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(output);
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function firstString(...values: unknown[]): string | undefined {
  return values.find((value): value is string => typeof value === 'string' && value.length > 0);
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

type ExecErrorOutput = {
  stdout: string;
  combined: string;
};

function outputFromExecError(error: unknown): ExecErrorOutput {
  if (typeof error !== 'object' || error === null) {
    const message = String(error);
    return { stdout: '', combined: message };
  }
  const withOutput = error as ExecErrorWithOutput;
  const stdout = typeof withOutput.stdout === 'string' ? withOutput.stdout : '';
  const combined = [withOutput.stdout, withOutput.stderr, withOutput.message]
    .filter((value): value is string => typeof value === 'string')
    .join('\n');
  return { stdout, combined };
}
