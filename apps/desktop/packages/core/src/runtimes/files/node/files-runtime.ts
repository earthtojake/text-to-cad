import { realpath } from 'node:fs/promises';
import { homedir } from 'node:os';
import path from 'node:path';
import {
  DEFAULT_WATCHER_EXCLUDE,
  normalizeExclusionPatterns,
} from '#primitives/exclusion-policy/api';
import { parseAbsolute, type HostAbsolutePath } from '#primitives/path/api';
import { FilesAllocationGraph } from '#runtimes/files/node/allocation/allocation-graph';
import { FileContentRuntime } from '#runtimes/files/node/content/content-runtime';
import { FileSystemRuntime } from '#runtimes/files/node/fs/file-system';
import { FileTreeRuntime } from '#runtimes/files/node/tree/tree-runtime';
import type { IWatchService } from '#services/fs-watch/api';
import { createNativeWatchService } from '#services/fs-watch/node';

export type FilesRuntimeOptions = {
  watcher?: IWatchService;
  watchIgnoreGlobs?: readonly string[];
  idleTtlMs?: number;
  maxContentBytes?: number;
  onError?: (context: string, error: unknown) => void;
};

export class FilesRuntime {
  readonly fs: FileSystemRuntime;
  readonly tree: FileTreeRuntime;
  readonly content: FileContentRuntime;

  private readonly allocations: FilesAllocationGraph;
  private readonly watcher: IWatchService;
  private readonly ownsWatcher: boolean;
  private disposed = false;

  constructor(options: FilesRuntimeOptions = {}) {
    const onError = options.onError ?? (() => {});
    this.ownsWatcher = options.watcher === undefined;
    this.watcher = options.watcher ?? createNativeWatchService({ onError });
    this.allocations = new FilesAllocationGraph({
      watcher: this.watcher,
      watchIgnoreGlobs: normalizeExclusionPatterns(
        options.watchIgnoreGlobs ?? DEFAULT_WATCHER_EXCLUDE
      ),
      idleTtlMs: options.idleTtlMs,
      maxContentBytes: options.maxContentBytes,
      onError,
    });
    this.fs = new FileSystemRuntime(this.allocations);
    this.tree = new FileTreeRuntime(this.allocations);
    this.content = new FileContentRuntime(this.allocations);
  }

  async getHomeDir(): Promise<{ path: HostAbsolutePath }> {
    const canonicalHome = await realpath(homedir());
    const parsed = parseAbsolute(canonicalHome, {
      profile: {
        style: path.sep === '\\' ? 'win32' : 'posix',
        unicodeNormalization: 'preserve',
      },
    });
    if (!parsed.success) {
      throw new Error(`Host home directory is not an absolute path: ${parsed.error.message}`);
    }
    return { path: parsed.data };
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    await Promise.all([this.content.dispose(), this.tree.dispose()]);
    await this.allocations.dispose();
    if (this.ownsWatcher) await this.watcher.dispose();
  }
}
