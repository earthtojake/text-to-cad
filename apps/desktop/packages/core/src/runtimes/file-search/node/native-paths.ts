import path from 'node:path';
import {
  parseAbsolute,
  parsePortableRelativePath,
  type HostAbsolutePath,
  type PortableRelativePath,
} from '#primitives/path/api';

export function hostAbsolutePathFromNative(nativePath: string): HostAbsolutePath {
  const parsed = parseAbsolute(nativePath, {
    profile: {
      style: path.sep === '\\' ? 'win32' : 'posix',
      unicodeNormalization: 'preserve',
    },
  });
  if (!parsed.success) throw new Error(parsed.error.message);
  return parsed.data;
}

export function containsNativePath(parent: string, child: string): boolean {
  const relative = path.relative(parent, child);
  return (
    relative === '' ||
    (relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative))
  );
}

export function sameNativePath(left: string, right: string): boolean {
  return containsNativePath(left, right) && containsNativePath(right, left);
}

export function portableRelativePathFromNative(
  rootPath: string,
  absolutePath: string
): PortableRelativePath | null {
  if (!containsNativePath(rootPath, absolutePath)) return null;
  const relative = path.relative(rootPath, absolutePath).split(path.sep).join('/');
  const parsed = parsePortableRelativePath(relative);
  return parsed.success ? parsed.data : null;
}

export function isPortablePathHostCompatible(relativePath: PortableRelativePath): boolean {
  return path.sep !== '\\' || !relativePath.includes('\\');
}
