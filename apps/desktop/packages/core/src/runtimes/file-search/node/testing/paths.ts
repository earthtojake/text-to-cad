import path from 'node:path';
import {
  parseAbsolute,
  parsePortableRelativePath,
  type HostAbsolutePath,
  type PortableRelativePath,
} from '#primitives/path/api';

export function hostPath(input: string): HostAbsolutePath {
  const parsed = parseAbsolute(input, {
    profile: {
      style: path.sep === '\\' ? 'win32' : 'posix',
      unicodeNormalization: 'preserve',
    },
  });
  if (!parsed.success) throw new Error(parsed.error.message);
  return parsed.data;
}

export function relativePath(input: string): PortableRelativePath {
  const parsed = parsePortableRelativePath(input, { unicodeNormalization: 'preserve' });
  if (!parsed.success) throw new Error(parsed.error.message);
  return parsed.data;
}
