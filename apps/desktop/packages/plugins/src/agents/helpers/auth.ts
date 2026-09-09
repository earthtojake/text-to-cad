import type {
  AgentAuthContext,
  AgentAuthStatus,
} from '@emdash/core/services/agent-plugins/api/plugins';

export function authenticatedFromEnv(
  ctx: AgentAuthContext,
  envVarNames: string[]
): AgentAuthStatus {
  return envVarNames.some((name) => Boolean(ctx.env[name]))
    ? { kind: 'authenticated' }
    : { kind: 'unknown' };
}

export async function commandAuthStatus(
  ctx: AgentAuthContext,
  args: string[],
  options: {
    authenticatedPattern?: RegExp;
    unauthenticatedPattern?: RegExp;
    timeout?: number;
  } = {}
): Promise<AgentAuthStatus> {
  try {
    const { stdout, stderr } = await ctx.exec(ctx.cli, args, {
      timeout: options.timeout ?? 5000,
    });
    const output = `${stdout}\n${stderr}`;
    if (options.unauthenticatedPattern?.test(output)) {
      return { kind: 'unauthenticated' };
    }
    if (!options.authenticatedPattern || options.authenticatedPattern.test(output)) {
      return { kind: 'authenticated' };
    }
    return { kind: 'unknown' };
  } catch (error) {
    const output = outputFromExecError(error);
    if (options.unauthenticatedPattern?.test(output)) {
      return { kind: 'unauthenticated' };
    }
    if (options.authenticatedPattern?.test(output)) {
      return { kind: 'authenticated' };
    }
    return { kind: 'unknown' };
  }
}

function outputFromExecError(error: unknown): string {
  if (typeof error !== 'object' || error === null) return String(error);
  const withOutput = error as { stdout?: unknown; stderr?: unknown; message?: unknown };
  return [withOutput.stdout, withOutput.stderr, withOutput.message]
    .filter((value): value is string => typeof value === 'string')
    .join('\n');
}
