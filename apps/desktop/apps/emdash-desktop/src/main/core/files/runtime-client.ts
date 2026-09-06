import path from 'node:path';
import type { HostAbsolutePath, PortableRelativePath } from '@emdash/core/primitives/path/api';
import type { FsError } from '@emdash/core/runtimes/files/api';
import type { Result } from '@emdash/shared';
import type {
  JobError,
  JobInput,
  JobProgress,
  JobResult,
  LiveJobClientHandle,
  LiveJobEndpointDef,
} from '@emdash/wire/rpc';
import {
  hostPathFromNative,
  nativePathFromHost,
  portablePath,
  relativePathWithin,
  resolveRelativePath,
} from '@core/primitives/desktop-runtime/api';
import { runRuntimeLiveJob } from '@main/core/runtime/live-job';
import type { FilesRuntimeClient } from '@main/gateway/desktop-workers';

export type FilesClientScope = {
  client: FilesRuntimeClient;
  root: HostAbsolutePath;
};

export type FileExclusionPredicate = (absolutePath: string) => boolean;

export function filesClientScope(client: FilesRuntimeClient, rootPath: string): FilesClientScope {
  const resolvedRoot = path.resolve(rootPath);
  return { client, root: hostPathFromNative(resolvedRoot) };
}

export function fileRelativePath(
  scope: Pick<FilesClientScope, 'root'>,
  targetPath: string
): PortableRelativePath {
  return relativePathWithin(scope.root, hostPathFromNative(path.resolve(targetPath)));
}

/**
 * The `fs` surface is keyed by host-absolute paths (spec §3.4). Resolving
 * through the scope's root keeps the historical containment check: a target
 * escaping the scope root still throws at this edge.
 */
export function fileKey(scope: FilesClientScope, targetPath: string): { path: HostAbsolutePath } {
  return { path: resolveRelativePath(scope.root, fileRelativePath(scope, targetPath)) };
}

export function nativeFilePath(scope: FilesClientScope, relative: PortableRelativePath): string {
  return nativePathFromHost(resolveRelativePath(scope.root, relative));
}

export function parentFilePaths(relative: PortableRelativePath): PortableRelativePath[] {
  const parts = relative.split('/');
  return parts.map((_, index) => portablePath(parts.slice(0, index + 1).join('/')));
}

export function runFilesJob<Def extends LiveJobEndpointDef>(
  definition: Def,
  handle: LiveJobClientHandle<Def>,
  input: JobInput<Def>,
  onProgress?: (progress: JobProgress<Def>) => void
): Promise<Result<JobResult<Def>, JobError<Def>>> {
  return runRuntimeLiveJob(definition, handle, input, onProgress);
}

export async function* singleFileChunk(bytes: Uint8Array): AsyncIterable<Uint8Array> {
  yield bytes;
}

export function fsErrorMessage(error: FsError): string {
  switch (error.type) {
    case 'invalid-path':
    case 'io':
      return error.message;
    case 'etag-mismatch':
      return `File changed since it was read: ${error.path}`;
    default:
      return `${error.type}: ${error.path}`;
  }
}

export function isFileNotFoundError(error: FsError): boolean {
  return error.type === 'not-found' || error.type === 'not-a-directory';
}
