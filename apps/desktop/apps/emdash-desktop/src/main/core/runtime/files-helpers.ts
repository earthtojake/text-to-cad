import path from 'node:path';
import type { FsError } from '@emdash/core/runtimes/files/api';
import { err, ok, type Result } from '@emdash/shared';
import { nativePathFromHost, resolveRelativePath } from '@core/primitives/desktop-runtime/api';
import {
  fileKey,
  fileRelativePath,
  filesClientScope,
  parentFilePaths,
  type FilesClientScope,
} from '@main/core/files/runtime-client';
import { isRealPathContained as isRealPathContainedByRealPath } from '../files/realpath-containment';

type FilesRuntimeClient = FilesClientScope['client'];
type GetFilesRuntimeClient = () => Promise<FilesRuntimeClient>;

export function createFilesHelpers(getFilesRuntimeClient: GetFilesRuntimeClient) {
  return {
    ensureAbsoluteDir: (rootPath: string, absPath: string, options: { recursive?: boolean } = {}) =>
      ensureAbsoluteDir(getFilesRuntimeClient, rootPath, absPath, options),
    realPathAbsolute: (rootPath: string, absPath: string) =>
      realPathAbsolute(getFilesRuntimeClient, rootPath, absPath),
    isRealPathContained: (
      rootPath: string,
      candidatePath: string,
      options: { candidateMustExist?: boolean } = {}
    ) => isRealPathContained(getFilesRuntimeClient, rootPath, candidatePath, options),
  };
}

async function openFilesClientScope(
  getFilesRuntimeClient: GetFilesRuntimeClient,
  rootPath: string
): Promise<Result<FilesClientScope, FsError>> {
  if (!path.isAbsolute(rootPath)) return err(expectedAbsolutePath(rootPath));
  return ok(filesClientScope(await getFilesRuntimeClient(), rootPath));
}

export async function ensureAbsoluteDir(
  getFilesRuntimeClient: GetFilesRuntimeClient,
  rootPath: string,
  absPath: string,
  options: { recursive?: boolean } = {}
): Promise<Result<void, FsError>> {
  if (!path.isAbsolute(rootPath)) return err(expectedAbsolutePath(rootPath));
  if (!path.isAbsolute(absPath)) return err(expectedAbsolutePath(absPath));
  const resolvedRoot = path.resolve(rootPath);
  const resolvedPath = path.resolve(absPath);
  if (!nativePathOperations.contains(resolvedRoot, resolvedPath)) {
    return err(expectedContainedPath(resolvedRoot, resolvedPath));
  }

  const recursive = options.recursive ?? true;
  const client = await getFilesRuntimeClient();
  const volumeRoot = path.parse(resolvedRoot).root;
  const rootReady = await ensureDirectory(filesClientScope(client, volumeRoot), resolvedRoot, {
    recursive,
  });
  if (!rootReady.success) return rootReady;

  return ensureDirectory(filesClientScope(client, resolvedRoot), resolvedPath, { recursive });
}

async function realPathAbsolute(
  getFilesRuntimeClient: GetFilesRuntimeClient,
  rootPath: string,
  absPath: string
): Promise<Result<string, FsError>> {
  const opened = await openFilesClientScope(getFilesRuntimeClient, rootPath);
  if (!opened.success) return opened;
  if (!path.isAbsolute(absPath)) return err(expectedAbsolutePath(absPath));
  const result = await opened.data.client.fs.realPath(fileKey(opened.data, absPath));
  return result.success ? ok(nativePathFromHost(result.data.path)) : result;
}

async function isRealPathContained(
  getFilesRuntimeClient: GetFilesRuntimeClient,
  rootPath: string,
  candidatePath: string,
  options: { candidateMustExist?: boolean } = {}
): Promise<Result<boolean, FsError>> {
  const opened = await openFilesClientScope(getFilesRuntimeClient, rootPath);
  if (!opened.success) return opened;
  if (!path.isAbsolute(candidatePath)) return err(expectedAbsolutePath(candidatePath));
  return isRealPathContainedByRealPath(
    opened.data,
    nativePathOperations,
    rootPath,
    candidatePath,
    options
  );
}

async function ensureDirectory(
  files: FilesClientScope,
  targetPath: string,
  options: { recursive?: boolean }
): Promise<Result<void, FsError>> {
  const relative = fileRelativePath(files, targetPath);
  if (!relative) return ok<void>();
  const candidates = options.recursive ? parentFilePaths(relative) : [relative];
  for (const candidate of candidates) {
    const key = { path: resolveRelativePath(files.root, candidate) };
    const exists = await files.client.fs.exists(key);
    if (!exists.success) return exists;
    if (exists.data.exists) continue;
    const created = await files.client.fs.createDirectory(key);
    if (!created.success && created.error.type !== 'already-exists') return created;
  }
  return ok<void>();
}

const nativePathOperations = {
  basename: path.basename,
  contains(parent: string, child: string): boolean {
    const relative = path.relative(parent, child);
    return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
  },
  dirname: path.dirname,
  join: path.join,
};

function expectedAbsolutePath(input: string): FsError {
  return { type: 'invalid-path', path: input, message: `Expected absolute path: ${input}` };
}

function expectedContainedPath(rootPath: string, input: string): FsError {
  return {
    type: 'invalid-path',
    path: input,
    message: `Expected path inside ${rootPath}: ${input}`,
  };
}
