import type { ClipboardPort } from '@text-to-cad/ui/host';
import type { FileActions, FileChange, FileEntry, FileMetadata, FileSource } from '@text-to-cad/ui/file-viewer';
import type { createCadClient, CadEntry } from '@text-to-cad/core/client';
import type { Root } from './server';
import { TUNNEL_ORIGIN } from './tunnel';

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

const directoriesFirst = (a: FileEntry, b: FileEntry) =>
  Number(b.kind === 'directory') - Number(a.kind === 'directory') || a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });

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
      return [...entries.values()].sort(directoriesFirst);
    },
    async paths({ signal }) { await ready(signal); return paths(); },
  };
}

/** The entry of `directory` on the way to `target`: the next folder down, or the file itself. */
function stepToward(directory: string, target: string | null): string | null {
  if (!target) return null;
  const rest = !directory ? target : target.startsWith(`${directory}/`) ? target.slice(directory.length + 1) : '';
  return rest ? (directory ? `${directory}/` : '') + rest.split('/')[0] : null;
}

/**
 * A whole filesystem, a folder at a time. A global root is never walked: the explorer reads each
 * folder it opens (`/__cad/list`), and the catalog holds only the file on screen. A folder no listing
 * shows (a hidden one) is still there when the open file is inside it, so the tree reaches the file.
 */
export function createFilesystemSource(client: CadClient, root: Root, fetchFolder: typeof fetch, { id, explore, showing }: {
  id: string; explore: boolean;
  /** The file on screen, root-relative. */
  showing: () => string | null;
}): FileSource {
  const catalog = createCatalogSource(client, root, { id, explore: false });
  const source: FileSource = {
    ...catalog,
    // A file coming or going in a catalog of the file on screen is another file shown, not the
    // disk changing: only a change to the file that stayed is one.
    subscribe: listener => catalog.subscribe!(change => {
      const changes = change.changes.filter(item => item.kind === 'content' || item.kind === 'metadata');
      if (changes.length) listener({ ...change, changes });
    }),
  };
  if (!explore) return source;
  const listed = new Map<string, readonly string[]>();
  return {
    ...source,
    async list(directory, { signal }) {
      const response = await fetchFolder(`${TUNNEL_ORIGIN}/__cad/list?dir=${encodeURIComponent(directory)}`, { signal });
      const body = await response.json().catch(() => null) as { entries?: FileEntry[]; error?: string } | null;
      if (!response.ok || !body?.entries) throw new Error(body?.error || `Could not read ${directory || root.name}.`);
      const entries: FileEntry[] = body.entries.map(({ path, name, kind }) => ({ path, name, kind }));
      const file = showing();
      const toward = stepToward(directory, file);
      if (toward && !entries.some(entry => entry.path === toward)) {
        entries.push({ path: toward, name: toward.split('/').pop() || toward, kind: toward === file ? 'file' : 'directory' });
      }
      listed.set(directory, entries.filter(entry => entry.kind === 'file').map(entry => entry.path));
      return entries.sort(directoriesFirst);
    },
    // The filter's corpus: the files of every folder read so far, since nothing walks the disk.
    async paths() { return [...new Set([...listed.values()].flat())]; },
  };
}

/** The file menu's copy actions: this host copies paths and reveals nothing. */
export function createFileActions(root: Root, clipboard: ClipboardPort, platform: string): FileActions {
  return {
    platform: platform === 'darwin' || platform === 'win32' ? platform : 'linux',
    perform: {
      // A path relative to a whole filesystem is its absolute path, less the first slash.
      ...(root.kind === 'global' ? {} : { 'copy-relative-path': (entry: { path: string }) => clipboard.writeText(entry.path) }),
      'copy-path': entry => clipboard.writeText(absolutePath(root, entry.path)),
    },
  };
}
