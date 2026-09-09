import { realpathSync } from 'node:fs';
import path from 'node:path';
import { formatAbsolute, parseAbsolute, type HostAbsolutePath } from '#primitives/path/api';

export function realpathOrResolve(filePath: string): string {
  try {
    return realpathSync.native(filePath);
  } catch {
    try {
      return realpathSync(filePath);
    } catch {
      return path.resolve(filePath);
    }
  }
}

export function toNativeAbsolutePath(hostPath: HostAbsolutePath): string {
  const style = path.sep === '\\' ? 'win32' : 'posix';
  const compatible =
    style === 'posix' ? hostPath.root.kind === 'posix' : hostPath.root.kind !== 'posix';
  if (!compatible) {
    throw new Error(`Path style is not valid on this host: ${formatAbsolute(hostPath)}`);
  }
  return formatAbsolute(hostPath, { separator: path.sep as '/' | '\\' });
}

export function toHostAbsolutePath(filePath: string): HostAbsolutePath {
  const canonical = realpathOrResolve(filePath);
  const parsed = parseAbsolute(canonical, {
    profile: {
      style: path.sep === '\\' ? 'win32' : 'posix',
      unicodeNormalization: 'preserve',
    },
  });
  if (!parsed.success) throw new Error(parsed.error.message);
  return parsed.data;
}
