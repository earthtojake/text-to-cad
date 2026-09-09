import { err, ok, type Result } from '@emdash/shared';
import { buildAllowlistedAgentEnv } from '#primitives/agent-env/api';
import type { EnvSource } from '#primitives/exec/api';

export type SpawnContext = {
  cli: string;
  agentEnv: Record<string, string>;
};

export type SpawnContextError =
  | { type: 'unknown-provider'; providerId: string }
  | { type: 'cli-not-found'; providerId: string; message: string };

export interface SpawnContextResolver {
  resolve(providerId: string): Promise<Result<SpawnContext, SpawnContextError>>;
  invalidate(providerId?: string): void;
}

export type CreateSpawnContextResolverOptions = {
  resolveCli: (providerId: string) => Promise<string>;
  env: EnvSource;
  homeDir: string;
  includeShellVar?: boolean;
  hasProvider?: (providerId: string) => boolean;
};

export function createSpawnContextResolver(
  options: CreateSpawnContextResolverOptions
): SpawnContextResolver {
  const resolve = async (providerId: string): Promise<Result<SpawnContext, SpawnContextError>> => {
    if (options.hasProvider && !options.hasProvider(providerId)) {
      return err({ type: 'unknown-provider', providerId });
    }

    try {
      return ok({ cli: await options.resolveCli(providerId), agentEnv: await buildAgentEnv() });
    } catch (error: unknown) {
      return err({
        type: 'cli-not-found',
        providerId,
        message: error instanceof Error ? error.message : String(error),
      });
    }
  };

  const invalidate = (_providerId?: string): void => {};

  return { resolve, invalidate };

  async function buildAgentEnv(): Promise<Record<string, string>> {
    return buildAllowlistedAgentEnv(await options.env(), {
      homeDir: options.homeDir,
      includeShellVar: options.includeShellVar,
    });
  }
}
