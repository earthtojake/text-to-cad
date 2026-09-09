const APPIMAGE_ENV_KEYS = [
  'APPDIR',
  'APPIMAGE',
  'ARGV0',
  'CHROME_DESKTOP',
  'GSETTINGS_SCHEMA_DIR',
  'OWD',
] as const;

const APPIMAGE_PATH_LIKE_ENV_KEYS = ['PATH', 'LD_LIBRARY_PATH', 'XDG_DATA_DIRS'] as const;

function stripPathLikeAppImageEntries(value: string, appDir?: string): string {
  const separator = process.platform === 'win32' ? ';' : ':';
  const parts = value.split(separator).filter(Boolean);
  if (parts.length === 0) return value;

  const filtered = parts.filter((part) => {
    if (appDir && part.startsWith(appDir)) return false;
    if (part.includes('/tmp/.mount_')) return false;
    return true;
  });

  return filtered.join(separator);
}

export function buildExternalToolEnv(baseEnv: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...baseEnv };
  const appDir = typeof baseEnv.APPDIR === 'string' ? baseEnv.APPDIR : undefined;

  for (const key of APPIMAGE_ENV_KEYS) {
    delete env[key];
  }

  for (const key of APPIMAGE_PATH_LIKE_ENV_KEYS) {
    const value = env[key];
    if (typeof value !== 'string' || value.length === 0) continue;
    const cleaned = stripPathLikeAppImageEntries(value, appDir);
    if (cleaned.length > 0) env[key] = cleaned;
    else delete env[key];
  }

  for (const key of ['PYTHONHOME', 'PYTHONPATH'] as const) {
    const value = env[key];
    if (typeof value !== 'string' || value.length === 0) continue;
    if ((appDir && value.startsWith(appDir)) || value.includes('/tmp/.mount_')) {
      delete env[key];
    }
  }

  return env;
}
