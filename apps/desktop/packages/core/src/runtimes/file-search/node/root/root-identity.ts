import { realpath, stat } from 'node:fs/promises';
import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import {
  comparisonKeyForAbsolutePath,
  createPathProfile,
  formatAbsolute,
  type HostAbsolutePath,
} from '#primitives/path/api';
import type { FileSearchRegisterRootError } from '#runtimes/file-search/api';
import { rootUnavailable, toExpectedRootOrIndexError } from '../error-mapping';
import { hostAbsolutePathFromNative } from '../native-paths';

export type ResolvedFileSearchRoot = Readonly<{
  rootKey: string;
  rootPath: string;
}>;

/** Resolves file-search roots to the canonical filesystem identity used by core runtimes. */
export class NodeFileSearchRootResolver {
  private readonly profile = createPathProfile({
    style: path.sep === '\\' ? 'win32' : 'posix',
  });

  comparisonKey(root: HostAbsolutePath): string {
    return comparisonKeyForAbsolutePath(root, this.profile);
  }

  async resolve(
    root: HostAbsolutePath
  ): Promise<Result<ResolvedFileSearchRoot, FileSearchRegisterRootError>> {
    const compatible = path.sep === '\\' ? root.root.kind !== 'posix' : root.root.kind === 'posix';
    if (!compatible) {
      return err(rootUnavailable(root, 'invalid-path', 'Path style is not valid on this host'));
    }

    const nativePath = formatAbsolute(root, { separator: path.sep as '/' | '\\' });
    if (!path.isAbsolute(nativePath) || nativePath.includes('\0')) {
      return err(rootUnavailable(root, 'invalid-path', 'Root must be a valid absolute path'));
    }

    try {
      const canonicalPath = await realpath(nativePath);
      const metadata = await stat(canonicalPath);
      if (!metadata.isDirectory()) {
        return err(rootUnavailable(root, 'not-a-directory', 'Root is not a directory'));
      }
      const canonicalRoot = hostAbsolutePathFromNative(canonicalPath);
      const rootKey = this.comparisonKey(canonicalRoot);
      if (this.comparisonKey(root) !== rootKey) {
        return err(
          rootUnavailable(
            root,
            'invalid-path',
            'File-search roots must use their canonical filesystem path'
          )
        );
      }
      return ok({ rootKey, rootPath: canonicalPath });
    } catch (error) {
      const expected = toExpectedRootOrIndexError(
        root,
        error,
        'Unable to resolve file-search root',
        'root'
      );
      if (expected) return err(expected);
      throw error;
    }
  }
}
