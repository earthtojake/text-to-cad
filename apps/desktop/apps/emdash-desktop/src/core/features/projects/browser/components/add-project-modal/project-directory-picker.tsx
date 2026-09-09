import {
  ROOT_RELATIVE_PATH,
  joinAbsolute,
  joinPortableRelativePath,
  portableRelativePathDirname,
  type HostAbsolutePath,
  type PortableRelativePath,
} from '@emdash/core/primitives/path/api';
import {
  type FileEntry,
  type FileTreeModel,
  isExpandableFileEntry,
} from '@emdash/core/runtimes/files/api';
import { createScope } from '@emdash/shared/concurrency';
import { runWithTimeout, TimeoutError } from '@emdash/shared/scheduling';
import {
  DirectorySelector,
  useDirectoryHistory,
  type DirectoryEntry,
  type DirectoryListing,
} from '@emdash/ui/react/components';
import { toast } from '@emdash/ui/react/primitives';
import { type Contract, type ContractClient } from '@emdash/wire/rpc';
import {
  observe,
  remote,
  whenReady,
  type RemoteModel,
  type RemoteMember,
} from '@emdash/wire/state';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  projectsWireContract,
  type ProjectHostParams,
  type ProjectsWireContract,
} from '@core/features/projects/api';
import {
  hostPathFromNative,
  nativePathFromHost,
  relativePathWithin,
} from '@core/primitives/desktop-runtime/api';
import { type Strategy } from './add-project-modal';

type DirectoryTreeModel = typeof projectsWireContract.directoryTree;
type DirectoryTreeRemote = RemoteModel<DirectoryTreeModel>;
type DirectoryTreeMember = RemoteMember<DirectoryTreeModel>;
type ContractDefinitionsOf<TContract> = TContract extends Contract<infer Defs> ? Defs : never;
const DIRECTORY_TREE_READY_TIMEOUT_MS = 30_000;
export type ProjectDirectoryPickerClient = ContractClient<
  ContractDefinitionsOf<ProjectsWireContract>
>;

type ProjectDirectoryPickerProps = {
  strategy: Strategy;
  connectionId?: string;
  initialPath?: string;
  homePath: string;
  homePending: boolean;
  homeError: Error | null;
  value: string;
  getProjectsClient(): Promise<ProjectDirectoryPickerClient>;
  onSelect(path: string): void;
};

export function ProjectDirectoryPicker({
  strategy,
  connectionId,
  initialPath,
  homePath,
  homePending,
  homeError,
  value,
  getProjectsClient,
  onSelect,
}: ProjectDirectoryPickerProps) {
  const host = useMemo(() => projectHostParams(strategy, connectionId), [connectionId, strategy]);
  const history = useDirectoryHistory(initialPath || homePath);
  const historyBackPath = history.backPath;
  const historyForwardPath = history.forwardPath;
  const historyBack = history.back;
  const historyForward = history.forward;
  const historyNavigate = history.navigate;
  const navigate = useCallback(
    (path: string) => {
      historyNavigate(path);
      onSelect(path);
    },
    [historyNavigate, onSelect]
  );
  const goBack = useCallback(() => {
    if (!historyBackPath) return;
    historyBack();
    onSelect(historyBackPath);
  }, [historyBack, historyBackPath, onSelect]);
  const goForward = useCallback(() => {
    if (!historyForwardPath) return;
    historyForward();
    onSelect(historyForwardPath);
  }, [historyForward, historyForwardPath, onSelect]);
  const root = useMemo(() => (homePath ? hostPathFromNative(homePath) : null), [homePath]);
  const sessionId = useMemo(() => crypto.randomUUID(), []);
  const tree = useProjectDirectoryTree(host, root, sessionId, getProjectsClient);
  const currentRelativePath = useMemo(() => {
    if (!root || !history.path) return ROOT_RELATIVE_PATH;
    return relativePathWithin(root, hostPathFromNative(history.path));
  }, [history.path, root]);
  const handleRevealNotFound = useCallback(
    (missingPath: PortableRelativePath) => {
      if (!root) return false;
      const parentPath = portableRelativePathDirname(missingPath);
      if (parentPath === null) return false;
      const parent = joinAbsolute(root, parentPath);
      if (!parent.success) return false;
      navigate(nativePathFromHost(parent.data));
      return true;
    },
    [navigate, root]
  );
  const reveal = useRevealDirectory(tree.member, currentRelativePath, handleRevealNotFound);

  const listing = directoryListing({
    homePending,
    homeError,
    syncError: tree.error ?? reveal.error,
    pending: reveal.pending,
    model: tree.model,
    path: currentRelativePath,
  });

  async function createFolder(_parentPath: string, name: string) {
    if (!root || !host) return;

    const childPath = joinPortableRelativePath(currentRelativePath, name);
    if (!childPath.success) {
      toast.error('Invalid folder name', { description: childPath.error.message });
      return;
    }

    const result = await (
      await getProjectsClient()
    ).createHostDirectory({
      host,
      root,
      path: childPath.data,
    });
    if (!result.success) {
      toast.error('Could not create folder', { description: fsErrorMessage(result.error) });
      return;
    }

    const createdPath = joinAbsolute(root, childPath.data);
    if (!createdPath.success) {
      toast.error('Could not select folder', { description: createdPath.error.message });
      return;
    }

    onSelect(nativePathFromHost(createdPath.data));
  }

  if (!host) {
    return (
      <div className="rounded-md border border-border bg-background-1 p-3 text-sm text-foreground-muted">
        Select a machine connection before browsing remote directories.
      </div>
    );
  }

  return (
    <DirectorySelector
      path={history.path || homePath}
      navigationRoot={homePath}
      listing={listing}
      selectedPath={value || null}
      canGoBack={history.canGoBack}
      canGoForward={history.canGoForward}
      onBack={goBack}
      onForward={goForward}
      onNavigate={navigate}
      onSelect={(path) => {
        if (path) onSelect(path);
      }}
      onCreateFolder={createFolder}
    />
  );
}

function useProjectDirectoryTree(
  host: ProjectHostParams | null,
  root: HostAbsolutePath | null,
  sessionId: string,
  getProjectsClient: () => Promise<ProjectDirectoryPickerClient>
): {
  member: DirectoryTreeMember | null;
  model: FileTreeModel | null;
  error: string | null;
} {
  const [member, setMember] = useState<DirectoryTreeMember | null>(null);
  const [model, setModel] = useState<FileTreeModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!host || !root) {
      setMember(null);
      setModel(null);
      return;
    }

    const currentHost = host;
    const currentRoot = root;
    let disposed = false;
    const scope = createScope({ label: `project-directory-picker:${sessionId}` });

    async function start() {
      try {
        const client = await getProjectsClient();
        if (disposed) return;
        const treeRemote: DirectoryTreeRemote = remote(
          projectsWireContract.directoryTree,
          client.directoryTree,
          { scope, lingerMs: 15_000 }
        );
        const treeMember = treeRemote(
          currentHost.type === 'ssh'
            ? {
                type: 'ssh',
                connectionId: currentHost.connectionId,
                root: currentRoot,
                sessionId,
              }
            : { type: 'local', root: currentRoot, sessionId }
        );
        observe(
          treeMember.states.tree,
          (snapshot) => {
            if (disposed) return;
            if (snapshot.status === 'error') {
              setError(errorMessage(snapshot.error));
              return;
            }
            setModel(snapshot.value ?? null);
          },
          { scope }
        );
        const ready = await runWithTimeout(() => whenReady(treeMember.states.tree, { scope }), {
          timeoutMs: DIRECTORY_TREE_READY_TIMEOUT_MS,
        });
        if (ready.status === 'error') throw ready.error;
        if (disposed) return;
        setMember(treeMember);
        setError(null);
      } catch (caught) {
        if (!disposed) {
          setError(
            caught instanceof TimeoutError
              ? 'The folder browser did not become ready within 30 seconds. The home directory may be too large to monitor.'
              : errorMessage(caught)
          );
        }
        void scope.dispose();
      }
    }

    void start();
    return () => {
      disposed = true;
      setMember(null);
      setModel(null);
      setError(null);
      void scope.dispose();
    };
  }, [getProjectsClient, host, root, sessionId]);

  return { member, model, error };
}

function useRevealDirectory(
  member: DirectoryTreeMember | null,
  path: PortableRelativePath,
  onNotFound: (path: PortableRelativePath) => boolean
): { pending: boolean; error: string | null } {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!member) return;
    const currentMember = member;
    let cancelled = false;
    setPending(true);
    setError(null);

    async function reveal() {
      try {
        const mutation = await currentMember.mutations.reveal({ path, depth: 2 });
        if (!mutation.result.success) {
          if (mutation.result.error.type === 'not-found' && onNotFound(path)) return;
          throw new Error(fsErrorMessage(mutation.result.error));
        }
        await mutation.settled;
        if (!cancelled) setError(null);
      } catch (caught) {
        if (!cancelled) setError(errorMessage(caught));
      } finally {
        if (!cancelled) setPending(false);
      }
    }

    void reveal();
    return () => {
      cancelled = true;
    };
  }, [member, onNotFound, path]);

  return { pending, error };
}

function directoryListing({
  homePending,
  homeError,
  syncError,
  pending,
  model,
  path,
}: {
  homePending: boolean;
  homeError: unknown;
  syncError: string | null;
  pending: boolean;
  model: FileTreeModel | null;
  path: PortableRelativePath;
}): DirectoryListing {
  if (homeError) return { status: 'error', message: errorMessage(homeError) };
  if (syncError) return { status: 'error', message: syncError };
  if (homePending || pending || !model) return { status: 'loading' };
  const entry = model.entries[path];
  if (!entry) return { status: 'loading' };
  if (!entry.childrenLoaded) return { status: 'loading' };
  return {
    status: 'ready',
    entries: entry.children.flatMap((childPath) => {
      const child = model.entries[childPath];
      return child ? [directoryEntry(child, model)] : [];
    }),
  };
}

function directoryEntry(entry: FileEntry, model: FileTreeModel): DirectoryEntry {
  const metadata = { sizeBytes: entry.size, addedAtMs: entry.mtimeMs };
  if (entry.kind === 'directory' && hasGitChild(entry, model)) {
    return { name: entry.name, kind: 'repository', ...metadata };
  }
  if (entry.kind === 'symlink' && entry.symlinkTargetKind === 'directory') {
    return { name: entry.name, kind: 'directory', ...metadata };
  }
  return { name: entry.name, kind: entry.kind, ...metadata };
}

function hasGitChild(entry: FileEntry, model: FileTreeModel): boolean {
  if (!isExpandableFileEntry(entry) || !entry.childrenLoaded) return false;
  return entry.children.some((childPath) => model.entries[childPath]?.name === '.git');
}

function projectHostParams(
  strategy: Strategy,
  connectionId: string | undefined
): ProjectHostParams | null {
  if (strategy === 'local') return { type: 'local' };
  return connectionId ? { type: 'ssh', connectionId } : null;
}

function fsErrorMessage(error: { type: string; path?: string; message?: string }): string {
  return error.message ?? `${error.type}${error.path ? `: ${error.path}` : ''}`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
