import path from 'node:path';
import type { Platform } from '#primitives/host-dependencies/api';

export type ConfigRootContext = {
  env: Record<string, string | undefined>;
  homeDir: string;
  platform: Platform;
};

export type ConfigRootResolver = (context: ConfigRootContext) => string;

function pathApi(platform: Platform): typeof path.posix {
  return platform === 'windows' ? path.win32 : path.posix;
}

function resolveOverride(value: string, homeDir: string, platform: Platform): string {
  return pathApi(platform).resolve(homeDir, value);
}

/** Resolve a provider configuration directory directly below the user's home directory. */
export function homeConfigRoot(directory: string): ConfigRootResolver {
  return ({ homeDir, platform }) => pathApi(platform).join(homeDir, directory);
}

/** Resolve an env-overridable provider directory, falling back below the user's home directory. */
export function envConfigRoot(envVar: string, fallbackDirectory: string): ConfigRootResolver {
  return ({ env, homeDir, platform }) =>
    env[envVar]
      ? resolveOverride(env[envVar], homeDir, platform)
      : pathApi(platform).join(homeDir, fallbackDirectory);
}

/** Combine multiple single-root resolvers into a multi-root resolver returning all roots. */
export function configRoots(
  ...resolvers: ConfigRootResolver[]
): (context: ConfigRootContext) => string[] {
  return (context) => resolvers.map((r) => r(context));
}

/**
 * Resolve an XDG-style configuration root. A provider-specific override wins first, followed by
 * XDG_CONFIG_HOME on POSIX or APPDATA on Windows, then the platform's conventional home fallback.
 */
export function xdgConfigRoot(
  directory: string,
  options: { overrideEnvVar?: string } = {}
): ConfigRootResolver {
  return ({ env, homeDir, platform }) => {
    const override = options.overrideEnvVar ? env[options.overrideEnvVar] : undefined;
    if (override) return resolveOverride(override, homeDir, platform);

    const paths = pathApi(platform);
    if (platform === 'windows') {
      const appData = env.APPDATA
        ? resolveOverride(env.APPDATA, homeDir, platform)
        : paths.join(homeDir, 'AppData', 'Roaming');
      return paths.join(appData, directory);
    }
    const xdgHome = env.XDG_CONFIG_HOME
      ? resolveOverride(env.XDG_CONFIG_HOME, homeDir, platform)
      : paths.join(homeDir, '.config');
    return paths.join(xdgHome, directory);
  };
}
