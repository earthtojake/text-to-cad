import { lstat, realpath, stat } from 'node:fs/promises';
import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import { portableRelativePathParts } from '#primitives/path/api';
import type { ContentSearchError, ContentSearchInput } from '#runtimes/file-search/api';
import { rootUnavailable, toExpectedContentScopeError } from '../error-mapping';
import { containsNativePath, isPortablePathHostCompatible, sameNativePath } from '../native-paths';

type ResolvedContentScope = Readonly<{
  rootPath: string;
  searchPath: string;
}>;

/** Validates that content search remains inside the canonical registered root. */
export async function resolveContentScope(
  rootPath: string,
  input: ContentSearchInput
): Promise<Result<ResolvedContentScope, ContentSearchError>> {
  if (input.under && !isPortablePathHostCompatible(input.under)) {
    return err(rootUnavailable(input.root, 'invalid-path', 'Search scope is invalid on this host'));
  }

  try {
    const canonicalRoot = await realpath(rootPath);
    if (!sameNativePath(rootPath, canonicalRoot)) {
      return err(
        rootUnavailable(
          input.root,
          'invalid-path',
          'Registered root no longer resolves to its original directory'
        )
      );
    }
    if (!(await stat(canonicalRoot)).isDirectory()) {
      return err(
        rootUnavailable(input.root, 'not-a-directory', 'Content-search root is not a directory')
      );
    }

    if (!input.under) return ok({ rootPath: canonicalRoot, searchPath: canonicalRoot });
    let current = canonicalRoot;
    for (const segment of portableRelativePathParts(input.under)) {
      current = path.join(current, segment);
      if ((await lstat(current)).isSymbolicLink()) {
        return err(
          rootUnavailable(
            input.root,
            'invalid-path',
            'Content-search scope cannot traverse a directory symlink'
          )
        );
      }
    }

    const canonicalScope = await realpath(current);
    if (!containsNativePath(canonicalRoot, canonicalScope)) {
      return err(
        rootUnavailable(input.root, 'invalid-path', 'Content-search scope leaves the root')
      );
    }
    if (!(await stat(canonicalScope)).isDirectory()) {
      return err(
        rootUnavailable(input.root, 'not-a-directory', 'Content-search scope is not a directory')
      );
    }
    return ok({ rootPath: canonicalRoot, searchPath: canonicalScope });
  } catch (error) {
    const expected = toExpectedContentScopeError(
      input.root,
      error,
      'Unable to resolve content-search scope'
    );
    if (expected) return err(expected);
    throw error;
  }
}
