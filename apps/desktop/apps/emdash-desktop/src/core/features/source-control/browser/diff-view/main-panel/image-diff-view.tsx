import type { GitFileSource } from '@emdash/core/runtimes/git/api';
import { useQuery } from '@tanstack/react-query';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { readImageFile } from '@core/features/files/api/browser/file-content';
import {
  checkoutSelector,
  getSourceControlClient,
  gitFilePath,
} from '@core/features/source-control/api/browser/client';
import { gitCheckoutStoreToken } from '@core/features/source-control/contributions/browser/workspace-store-tokens';
import type { ActiveFile } from '@core/features/tasks/contributions/mementos';
import { useWorkspace } from '@core/features/workbench/api/browser/task-composition-context';
import { resolveWorkspacePath } from '@core/features/workspaces/api/browser/workspace-path';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { formatBytes } from '@core/primitives/formatting/browser/formatBytes';
import { HEAD_REF, type GitRef } from '@core/primitives/git/api';
import { gitRefToString } from '@core/primitives/git/api';

interface ImageDiffViewProps {
  projectId: string;
  workspaceId: string;
  activeFile: ActiveFile;
}

type UnavailableReason = 'too-large' | 'lfs-pointer' | 'git-error';

type SideState =
  | { status: 'loading' }
  | { status: 'ready'; dataUrl: string; mimeType: string; size: number }
  | { status: 'missing' }
  | { status: 'unavailable'; reason: UnavailableReason }
  | { status: 'error'; message: string };

type Side = 'original' | 'modified';

function unavailableMessage(reason: UnavailableReason): string {
  switch (reason) {
    case 'too-large':
      return 'Preview unavailable — file is too large';
    case 'lfs-pointer':
      return 'Preview unavailable — Git LFS smudge filter not applied';
    case 'git-error':
      return 'Preview unavailable';
  }
}

// Working-tree ("unstaged") content lives on disk, not behind a git source.
function gitSourceForRef(ref: GitRef): GitFileSource | null {
  if (ref.kind === 'head') return { kind: 'head' };
  if (ref.kind === 'staged') return { kind: 'index' };
  if (ref.kind === 'unstaged') return null;
  return { kind: 'revision', revision: ref };
}

function downloadErrorState(error: { type: string }): SideState {
  switch (error.type) {
    case 'missing':
      return { status: 'missing' };
    case 'too-large':
      return { status: 'unavailable', reason: 'too-large' };
    case 'lfs-pointer':
      return { status: 'unavailable', reason: 'lfs-pointer' };
    case 'git_error':
    case 'resolution_failed':
      return { status: 'unavailable', reason: 'git-error' };
    default:
      return { status: 'error', message: 'Failed to load image' };
  }
}

async function loadFromGit(
  workspaceId: string,
  filePath: string,
  source: GitFileSource
): Promise<SideState> {
  const client = await getSourceControlClient();
  const result = await client.checkout.download({
    ...checkoutSelector(workspaceId),
    path: gitFilePath(filePath),
    source,
  });
  if (!result.success) return downloadErrorState(result.error);
  const bytes = await result.data.bytes();
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  const mimeType = result.data.meta.mimeType;
  const dataUrl = await blobToDataUrl(new Blob([buffer], { type: mimeType }));
  return { status: 'ready', dataUrl, mimeType, size: result.data.meta.size };
}

function loadFromRef(workspaceId: string, filePath: string, ref: GitRef): Promise<SideState> {
  const source = gitSourceForRef(ref);
  if (!source) {
    return Promise.resolve<SideState>({ status: 'unavailable', reason: 'git-error' });
  }
  return loadFromGit(workspaceId, filePath, source);
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener('load', () => resolve(String(reader.result)), { once: true });
    reader.addEventListener('error', () => reject(reader.error ?? new Error('Image read failed')), {
      once: true,
    });
    reader.readAsDataURL(blob);
  });
}

async function loadFromDisk(
  workspacePath: string,
  sshConnectionId: string | undefined,
  filePath: string
): Promise<SideState> {
  const res = await readImageFile(
    hostFileRefFromNativePath(resolveWorkspacePath(workspacePath, filePath), sshConnectionId)
  );
  if (!res.success) {
    return res.error.type === 'not-found' || res.error.type === 'not-a-directory'
      ? { status: 'missing' }
      : { status: 'unavailable', reason: 'git-error' };
  }
  const image = res.data;
  if (image.truncated) return { status: 'unavailable', reason: 'too-large' };
  return {
    status: 'ready',
    dataUrl: image.dataUrl,
    mimeType: image.mimeType ?? 'application/octet-stream',
    size: image.size ?? 0,
  };
}

function loadOriginal(workspaceId: string, activeFile: ActiveFile): Promise<SideState> {
  const ref: GitRef = activeFile.group === 'staged' ? HEAD_REF : activeFile.originalRef;
  return loadFromRef(workspaceId, activeFile.path, ref);
}

function loadModified(
  workspaceId: string,
  workspacePath: string,
  sshConnectionId: string | undefined,
  activeFile: ActiveFile
): Promise<SideState> {
  switch (activeFile.group) {
    case 'disk':
      return loadFromDisk(workspacePath, sshConnectionId, activeFile.path);
    case 'staged':
      return loadFromGit(workspaceId, activeFile.path, { kind: 'index' });
    case 'git':
    case 'pr':
      return loadFromRef(workspaceId, activeFile.path, activeFile.modifiedRef ?? HEAD_REF);
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function shouldRetryModifiedLoad(state: SideState): boolean {
  return (
    state.status === 'error' || (state.status === 'unavailable' && state.reason === 'git-error')
  );
}

async function loadModifiedWithTransientRetry(
  workspaceId: string,
  workspacePath: string,
  sshConnectionId: string | undefined,
  activeFile: ActiveFile
): Promise<SideState> {
  const delays = [120, 300, 600];
  let state = await loadModified(workspaceId, workspacePath, sshConnectionId, activeFile);

  for (const ms of delays) {
    if (!shouldRetryModifiedLoad(state)) return state;
    await delay(ms);
    state = await loadModified(workspaceId, workspacePath, sshConnectionId, activeFile);
  }

  return state;
}

function ImageSidePanel({ label, state, side }: { label: string; state: SideState; side: Side }) {
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
      <div className="flex shrink-0 items-baseline gap-2 border-b border-border px-3 py-2">
        <span className="font-sans text-xs text-foreground-muted">{label}</span>
        {state.status === 'ready' && (
          <span className="font-sans text-micro text-foreground-passive">
            {formatBytes(state.size)}
          </span>
        )}
      </div>
      <div className="flex flex-1 items-center justify-center overflow-auto p-4">
        <ImageSideContent state={state} side={side} />
      </div>
    </div>
  );
}

function ImageSideContent({ state, side }: { state: SideState; side: Side }) {
  switch (state.status) {
    case 'loading':
      return <div className="text-xs text-foreground-passive">Loading…</div>;
    case 'missing':
      return (
        <div className="text-xs text-foreground-passive">
          {side === 'original' ? 'File added' : 'File deleted'}
        </div>
      );
    case 'unavailable':
      return (
        <div className="text-xs text-foreground-passive">{unavailableMessage(state.reason)}</div>
      );
    case 'error':
      return <div className="text-xs text-foreground-passive">{state.message}</div>;
    case 'ready':
      return <PreviewImage state={state} alt={side} />;
  }
}

function PreviewImage({
  state,
  alt,
}: {
  state: Extract<SideState, { status: 'ready' }>;
  alt: string;
}) {
  const [decodeFailed, setDecodeFailed] = useState(false);

  if (decodeFailed) {
    return <div className="text-xs text-foreground-passive">Failed to decode image</div>;
  }

  return (
    <img
      key={state.dataUrl}
      src={state.dataUrl}
      alt={alt}
      className="max-h-full max-w-full object-contain"
      onError={() => setDecodeFailed(true)}
    />
  );
}

export const ImageDiffView = observer(function ImageDiffView({
  projectId,
  workspaceId,
  activeFile,
}: ImageDiffViewProps) {
  const workspace = useWorkspace();
  const git = workspace.get(gitCheckoutStoreToken);

  const fileKey = `${activeFile.path}|${activeFile.group}|${gitRefToString(activeFile.originalRef)}|${activeFile.modifiedRef ? gitRefToString(activeFile.modifiedRef) : ''}`;

  // For disk/staged groups the bytes can change without fileKey changing
  // (in-place overwrite, re-stage). Pinning to statusRevision reruns the
  // load whenever GitCheckoutStore observes an fs-watch or index event.
  const reactiveRevision =
    activeFile.group === 'disk' || activeFile.group === 'staged' ? git.statusRevision : 0;

  const placeholder: SideState = { status: 'loading' };

  const originalQuery = useQuery({
    queryKey: ['image-diff', 'original', projectId, workspaceId, fileKey, reactiveRevision],
    queryFn: () => loadOriginal(workspaceId, activeFile),
    placeholderData: placeholder,
    staleTime: Infinity,
  });

  const modifiedQuery = useQuery({
    queryKey: ['image-diff', 'modified', projectId, workspaceId, fileKey, reactiveRevision],
    queryFn: () =>
      loadModifiedWithTransientRetry(
        workspaceId,
        workspace.path,
        workspace.sshConnectionId,
        activeFile
      ),
    placeholderData: placeholder,
    staleTime: Infinity,
  });

  const original = originalQuery.data ?? placeholder;
  const modified = modifiedQuery.data ?? placeholder;

  return (
    <div className="flex h-full min-h-0 w-full">
      <ImageSidePanel label="Original" state={original} side="original" />
      <div className="w-px shrink-0 bg-border" />
      <ImageSidePanel label="Modified" state={modified} side="modified" />
    </div>
  );
});
