import path from 'node:path';

export function getWindowsEnvKey(env: NodeJS.ProcessEnv, key: string): string | undefined {
  if (env[key] !== undefined) return key;

  const lowerKey = key.toLowerCase();
  return Object.keys(env).find((candidate) => candidate.toLowerCase() === lowerKey);
}

export function getWindowsEnvValue(env: NodeJS.ProcessEnv, key: string): string | undefined {
  const envKey = getWindowsEnvKey(env, key);
  return envKey ? env[envKey] : undefined;
}

export function getWindowsPathEnvKey(env: NodeJS.ProcessEnv): string {
  return getWindowsEnvKey(env, 'PATH') ?? 'PATH';
}

export function prependWindowsPathEntry(env: NodeJS.ProcessEnv, entry: string): boolean {
  const pathKey = getWindowsPathEnvKey(env);
  const entries = (env[pathKey] ?? '').split(path.win32.delimiter).filter(Boolean);
  const existing = new Set(entries.map((item) => item.toLowerCase()));

  if (existing.has(entry.toLowerCase())) {
    return false;
  }

  env[pathKey] = [entry, ...entries].join(path.win32.delimiter);
  return true;
}

export function windowsNpmGlobalBin(env: NodeJS.ProcessEnv): string | null {
  const appData = getWindowsEnvValue(env, 'APPDATA');
  return appData ? path.win32.join(appData, 'npm') : null;
}

export function ensureWindowsNpmGlobalBinInPath(
  env: NodeJS.ProcessEnv = process.env
): string | null {
  const npmPath = windowsNpmGlobalBin(env);
  if (!npmPath) return null;
  return prependWindowsPathEntry(env, npmPath) ? npmPath : null;
}
