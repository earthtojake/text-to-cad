import type { FsError } from '@emdash/core/runtimes/files/api';
import { err, ok, type Result } from '@emdash/shared';
import { nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import { fileKey, isFileNotFoundError, type FilesClientScope } from './runtime-client';

export type RealPathPathOperations = {
  basename(path: string): string;
  contains(parent: string, child: string): boolean;
  dirname(path: string): string;
  join(basePath: string, ...segments: string[]): string;
};

export type RealPathContainmentOptions = {
  candidateMustExist?: boolean;
  candidateErrorMode?: 'outside' | 'error';
};

export async function realPathNearestExisting(
  files: FilesClientScope,
  pathOperations: RealPathPathOperations,
  absPath: string
): Promise<Result<string, FsError>> {
  let current = absPath;
  const tail: string[] = [];

  for (;;) {
    const real = await files.client.fs.realPath(fileKey(files, current));
    if (real.success) {
      const nativeRealPath = nativePathFromHost(real.data.path);
      return ok(
        tail.length
          ? pathOperations.join(nativeRealPath, ...tail.slice().reverse())
          : nativeRealPath
      );
    }
    if (!isFileNotFoundError(real.error)) return real;

    const parent = pathOperations.dirname(current);
    if (parent === current || parent === '.' || parent === '') {
      return err({
        type: 'invalid-path',
        path: absPath,
        message: `No existing ancestor for path: ${absPath}`,
      });
    }
    tail.push(pathOperations.basename(current));
    current = parent;
  }
}

export async function isRealPathContained(
  files: FilesClientScope,
  pathOperations: RealPathPathOperations,
  rootPath: string,
  candidatePath: string,
  options: RealPathContainmentOptions = {}
): Promise<Result<boolean, FsError>> {
  const rootReal = await files.client.fs.realPath(fileKey(files, rootPath));
  if (!rootReal.success) return rootReal;
  const nativeRootReal = nativePathFromHost(rootReal.data.path);

  const candidateReal = options.candidateMustExist
    ? await files.client.fs
        .realPath(fileKey(files, candidatePath))
        .then((result) => (result.success ? ok(nativePathFromHost(result.data.path)) : result))
    : await realPathNearestExisting(files, pathOperations, candidatePath);
  if (!candidateReal.success) {
    return options.candidateErrorMode === 'error' ? candidateReal : ok(false);
  }

  return ok(
    candidateReal.data === nativeRootReal ||
      pathOperations.contains(nativeRootReal, candidateReal.data)
  );
}
