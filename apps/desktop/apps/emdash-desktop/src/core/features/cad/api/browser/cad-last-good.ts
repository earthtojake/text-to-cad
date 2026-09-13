import { encodeResourceUri } from '@emdash/core/primitives/path/api';
import type { CadLastGoodSnapshot } from '@core/features/cad/api/cad-model-state';
import { getFilesClient } from '@core/features/files/api/browser/client';
import { resolveWorkspacePath } from '@core/features/workspaces/api/browser/workspace-path';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';

export function shouldAutoRestoreCadBackup(
  runId: string,
  locallyStartedRunId: string | null
): boolean {
  return runId === locallyStartedRunId;
}

export function shouldMarkCadRunInterrupted(options: {
  runStatus: string;
  runId: string;
  observedWorkingRunId: string | null;
  isWorking: boolean;
  lifecycleStatus?: string | null;
  agentStatus?: string | null;
}): boolean {
  return (
    options.runStatus === 'generating' &&
    options.observedWorkingRunId === options.runId &&
    !options.isWorking &&
    options.lifecycleStatus === 'idle' &&
    options.agentStatus === 'idle'
  );
}

export async function preserveLastGoodModel(options: {
  workspacePath: string;
  modelPath: string;
  sourcePath?: string;
  contextKey: string;
  runId: string;
  sshConnectionId?: string;
  recordedAt: string;
}): Promise<CadLastGoodSnapshot | undefined> {
  const client = await getFilesClient();
  const uri = (path: string) =>
    encodeResourceUri(hostFileRefFromNativePath(path, options.sshConnectionId));
  const modelExists = await fileExists(
    client,
    uri(resolveWorkspacePath(options.workspacePath, options.modelPath))
  );
  // cadgen 0.5 writes one optional declarations sidecar beside a STEP that
  // needs one (kinematics, animation, mesh exports). It is part of the
  // accepted artifact, never its source, so it is preserved and restored with
  // the STEP bytes.
  const sidecarPath = cadSidecarPath(options.modelPath);
  const sidecarExists = sidecarPath
    ? await fileExists(client, uri(resolveWorkspacePath(options.workspacePath, sidecarPath)))
    : false;
  const distinctSourcePath =
    options.sourcePath && options.sourcePath !== options.modelPath ? options.sourcePath : undefined;
  const sourceExists = distinctSourcePath
    ? await fileExists(client, uri(resolveWorkspacePath(options.workspacePath, distinctSourcePath)))
    : false;
  if (!modelExists && !sourceExists) return undefined;

  const backupRoot = resolveWorkspacePath(options.workspacePath, '.hardcore');
  const backupDirectory = resolveWorkspacePath(options.workspacePath, '.hardcore/last-good');
  for (const directory of [backupRoot, backupDirectory]) {
    const directoryExists = await client.fs.exists({ uri: uri(directory) });
    if (!directoryExists.success) throw new Error(fileErrorMessage(directoryExists.error));
    if (directoryExists.data.exists) continue;
    const created = await client.fs.createDirectory({ uri: uri(directory) });
    if (!created.success) throw new Error(fileErrorMessage(created.error));
  }

  const extension = modelExtension(options.modelPath);
  const modelKey = encodeURIComponent(options.contextKey.slice('cad-model:'.length));
  const backupPath = `.hardcore/last-good/${modelKey}-${options.runId}${extension}`;
  const sidecarBackupPath = `${backupPath}.json`;
  const sourceBackupPath = distinctSourcePath
    ? `.hardcore/last-good/${modelKey}-${options.runId}.source${modelExtension(distinctSourcePath)}`
    : undefined;
  let modelHash: string | undefined;
  let sourceHash: string | undefined;
  if (modelExists) {
    const backupUri = uri(resolveWorkspacePath(options.workspacePath, backupPath));
    await copyFile(
      client,
      uri(resolveWorkspacePath(options.workspacePath, options.modelPath)),
      backupUri
    );
    modelHash = await sha256File(client, backupUri, backupPath);
  }
  if (modelExists && sidecarExists && sidecarPath) {
    await copyFile(
      client,
      uri(resolveWorkspacePath(options.workspacePath, sidecarPath)),
      uri(resolveWorkspacePath(options.workspacePath, sidecarBackupPath))
    );
  }
  if (sourceExists && distinctSourcePath && sourceBackupPath) {
    const sourceBackupUri = uri(resolveWorkspacePath(options.workspacePath, sourceBackupPath));
    await copyFile(
      client,
      uri(resolveWorkspacePath(options.workspacePath, distinctSourcePath)),
      sourceBackupUri
    );
    sourceHash = await sha256File(client, sourceBackupUri, sourceBackupPath);
  }
  return {
    modelPath: options.modelPath,
    ...(modelExists ? { backupPath } : {}),
    ...(modelExists && sidecarPath ? { sidecarPath } : {}),
    ...(modelExists && sidecarExists && sidecarPath ? { sidecarBackupPath } : {}),
    ...(sourceExists && distinctSourcePath && sourceBackupPath
      ? { sourcePath: distinctSourcePath, sourceBackupPath }
      : {}),
    recordedAt: options.recordedAt,
    validationStatus: 'unknown',
    ...(modelHash ? { revisionId: `sha256:${modelHash}`, modelHash } : {}),
    ...(sourceHash ? { sourceHash } : {}),
  };
}

export async function restoreLastGoodModel(options: {
  workspacePath: string;
  snapshot: CadLastGoodSnapshot;
  sshConnectionId?: string;
  restoreSource?: boolean;
}): Promise<void> {
  const client = await getFilesClient();
  const uri = (path: string) =>
    encodeResourceUri(hostFileRefFromNativePath(path, options.sshConnectionId));
  const entries = [
    options.snapshot.backupPath
      ? { from: options.snapshot.backupPath, to: options.snapshot.modelPath }
      : null,
    options.restoreSource !== false &&
    options.snapshot.sourceBackupPath &&
    options.snapshot.sourcePath
      ? { from: options.snapshot.sourceBackupPath, to: options.snapshot.sourcePath }
      : null,
  ].filter((entry): entry is { from: string; to: string } => entry !== null);
  if (entries.length === 0) throw new Error('No recovery files are available.');

  for (const entry of entries) {
    const backupUri = uri(resolveWorkspacePath(options.workspacePath, entry.from));
    const backup = await readCompleteFile(client, backupUri, entry.from);
    const bytes = backup.bytes;
    const buffer = new ArrayBuffer(bytes.byteLength);
    new Uint8Array(buffer).set(bytes);
    const file = new Blob([buffer], { type: backup.mimeType });
    const restored = await client.fs.upload(
      {
        uri: uri(resolveWorkspacePath(options.workspacePath, entry.to)),
        overwrite: true,
      },
      {
        name: entry.to.split('/').at(-1) ?? entry.to,
        mimeType: file.type || 'application/octet-stream',
        size: file.size,
        lastModified: Date.now(),
        source: file.stream(),
      }
    );
    if (!restored.success) throw new Error(fileErrorMessage(restored.error));
  }

  // Render trees are keyed by STEP bytes: restoring the file restores its
  // render identity without deleting or rewriting any cadgen store entries.

  // Bring the sidecar back to the accepted state as well: restore the copy
  // that belonged to the STEP, or remove one a failed rebuild left behind.
  if (options.snapshot.backupPath && options.snapshot.sidecarPath) {
    const sidecarUri = uri(
      resolveWorkspacePath(options.workspacePath, options.snapshot.sidecarPath)
    );
    if (options.snapshot.sidecarBackupPath) {
      await copyFile(
        client,
        uri(resolveWorkspacePath(options.workspacePath, options.snapshot.sidecarBackupPath)),
        sidecarUri
      );
    } else if (await fileExists(client, sidecarUri)) {
      const removed = await client.fs.delete({ uri: sidecarUri });
      if (!removed.success) throw new Error(fileErrorMessage(removed.error));
    }
  }
}

export function cadSidecarPath(modelPath: string): string | null {
  return /\.(?:step|stp)$/i.test(modelPath) ? `${modelPath}.json` : null;
}

async function sha256File(
  client: Awaited<ReturnType<typeof getFilesClient>>,
  uri: ReturnType<typeof encodeResourceUri>,
  path: string
): Promise<string> {
  const { bytes } = await readCompleteFile(client, uri, path);
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  const digest = await globalThis.crypto.subtle.digest('SHA-256', buffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function readCompleteFile(
  client: Awaited<ReturnType<typeof getFilesClient>>,
  uri: ReturnType<typeof encodeResourceUri>,
  path: string
): Promise<{ bytes: Uint8Array; mimeType: string }> {
  let result = await client.fs.readBytes({ uri });
  if (!result.success) throw new Error(fileErrorMessage(result.error));
  if (result.data.meta.truncated) {
    result = await client.fs.readBytes({
      uri,
      options: { maxBytes: result.data.meta.totalSize },
    });
    if (!result.success) throw new Error(fileErrorMessage(result.error));
  }
  if (result.data.meta.truncated) throw new Error(`Recovery file is incomplete: ${path}`);
  return {
    bytes: await result.data.bytes(),
    mimeType: result.data.meta.mimeType || 'application/octet-stream',
  };
}

async function fileExists(
  client: Awaited<ReturnType<typeof getFilesClient>>,
  uri: ReturnType<typeof encodeResourceUri>
): Promise<boolean> {
  const existing = await client.fs.exists({ uri });
  if (!existing.success) throw new Error(fileErrorMessage(existing.error));
  return existing.data.exists;
}

async function copyFile(
  client: Awaited<ReturnType<typeof getFilesClient>>,
  from: ReturnType<typeof encodeResourceUri>,
  to: ReturnType<typeof encodeResourceUri>
): Promise<void> {
  const copied = await client.fs.copy({ from, to });
  if (!copied.success) throw new Error(fileErrorMessage(copied.error));
}

function modelExtension(path: string): string {
  const filename = path.split('/').at(-1) ?? '';
  const dot = filename.lastIndexOf('.');
  return dot > 0 ? filename.slice(dot) : '.cad';
}

function fileErrorMessage(error: { type: string; message?: string }): string {
  return error.message ?? error.type;
}
