import type { ClipboardPort } from '@text-to-cad/ui/host';
import type { FileActions, FileChange, FileEntry, FileMetadata, FileSource } from '@text-to-cad/ui/file-viewer';
import type { createCadClient, CadEntry } from '@text-to-cad/core/client';
import type { Root } from './server';

export type CadClient = ReturnType<typeof createCadClient>;

/** A catalog entry's path under its root, the path the viewer shows and references carry. */
export const catalogPath = (entry: CadEntry): string =>
  String(entry.rootRelativeFile || entry.file || '').trim().replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/+$/, '');

const separator = (root: Pick<Root, 'path'>) => (root.path.includes('\\') && !root.path.includes('/') ? '\\' : '/');

/** The absolute path of `relative` under `root`. */
export function absolutePath(root: Pick<Root, 'path'>, relative: string): string {
  const sep = separator(root);
  return `${root.path.replace(/[\\/]+$/, '')}${sep}${sep === '\\' ? relative.replace(/\//g, '\\') : relative}`;
}

/** `model` relative to `root`, or null when it is not under it. */
export function relativePath(root: Pick<Root, 'path'>, model: string): string | null {
  const base = root.path.replace(/\\/g, '/').replace(/\/+$/, '');
  const path = model.replace(/\\/g, '/');
  return path.startsWith(`${base}/`) ? path.slice(base.length + 1) : null;
}

/** Render-affecting revisions, not transient compiler progress, invalidate the document. */
function contentRevision(entry: CadEntry): string {
  return JSON.stringify([entry.hash, entry.documentHash, entry.animationHash, entry.appearanceHash, entry.url, entry.relations, entry.sourceSidecar, entry.mtime, entry.bytes]);
}

/**
 * The files under a root, read-only, from the viewer's catalog. `explore` decides whether the
 * source can be browsed: without it there is no listing, so the viewer shows the one file with
 * no tree and no crumbs.
 */
export function createCatalogSource(client: CadClient, root: Root, { id, explore }: { id: string; explore: boolean }): FileSource {
  const paths = () => client.getSnapshot().entries.map(catalogPath).filter(Boolean);
  async function ready(signal: AbortSignal) {
    signal.throwIfAborted();
    if (!client.getSnapshot().hydrated) await client.refresh({ signal });
    signal.throwIfAborted();
  }
  const source: FileSource = {
    id,
    rootName: root.name,
    async stat(path, { signal }): Promise<FileMetadata> {
      const entry = await client.resolveEntry(path, { signal });
      signal.throwIfAborted();
      const relative = catalogPath(entry);
      return { path: relative, name: relative.split('/').pop() || relative, kind: 'file', size: Number(entry.bytes || 0), extension: relative.split('.').pop()?.toLowerCase() || '', mediaType: 'cad', revision: contentRevision(entry) };
    },
    subscribe(listener) {
      let previous = client.getSnapshot().entries;
      return client.subscribe(() => {
        const current = client.getSnapshot().entries;
        if (current === previous) return;
        const before = new Map(previous.map(entry => [catalogPath(entry), entry]));
        const after = new Map(current.map(entry => [catalogPath(entry), entry]));
        const changes: FileChange[] = [];
        for (const path of new Set([...before.keys(), ...after.keys()])) {
          const oldEntry = before.get(path), entry = after.get(path);
          if (!oldEntry) changes.push({ kind: 'added', path, entryKind: 'file' });
          else if (!entry) changes.push({ kind: 'deleted', path, entryKind: 'file' });
          else if (contentRevision(oldEntry) !== contentRevision(entry)) changes.push({ kind: 'content', path, revision: contentRevision(entry) });
          else if (JSON.stringify(oldEntry) !== JSON.stringify(entry)) changes.push({ kind: 'metadata', path });
        }
        previous = current;
        if (changes.length) listener({ sourceId: id, changes });
      });
    },
  };
  if (!explore) return source;
  return {
    ...source,
    async list(directory, { signal }) {
      await ready(signal);
      const prefix = directory ? `${directory}/` : '';
      const entries = new Map<string, FileEntry>();
      for (const path of paths()) {
        if (!path.startsWith(prefix)) continue;
        const rest = path.slice(prefix.length);
        if (!rest) continue;
        const name = rest.split('/')[0];
        const child = prefix + name;
        entries.set(child, { path: child, name, kind: rest.includes('/') ? 'directory' : 'file' });
      }
      return [...entries.values()].sort((a, b) => Number(b.kind === 'directory') - Number(a.kind === 'directory') || a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }));
    },
    async paths({ signal }) { await ready(signal); return paths(); },
  };
}

/** The file menu's copy actions: this host copies paths and reveals nothing. */
export function createFileActions(root: Root, clipboard: ClipboardPort, platform: string): FileActions {
  return {
    platform: platform === 'darwin' || platform === 'win32' ? platform : 'linux',
    perform: {
      'copy-relative-path': entry => clipboard.writeText(entry.path),
      'copy-path': entry => clipboard.writeText(absolutePath(root, entry.path)),
    },
  };
}
