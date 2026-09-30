import type { CadEntry, CadWorkspaceService } from '@text-to-cad/core/client';
import type { ResourceRef } from '@text-to-cad/core/prompt';
import type { ClipboardPort } from '../host/types.js';
import type { FileActions, FileChange, FileEntry, FileMetadata, FileSource } from '../file-viewer/types.js';

/**
 * `@text-to-cad/ui/catalog`: a CAD catalog as the viewer browses it, and the paths it is named by.
 * Pure — no React and no transport — so a host's adapters and their unit tests import it alone.
 *
 * A root's files are its catalog's: every entry a CAD client lists, by the path under the root it
 * is served from. The source a host hands the viewer (`createCatalogFileSource`), the file menu's
 * copies and reveal (`createCadFileActions`) and a prompt reference's path (`referencePath`) all
 * name a file the same way, whichever app hosts the view.
 */

/** A catalog entry's path under its root: what the viewer shows and references carry. */
export const catalogPath = (entry: CadEntry): string =>
  String(entry.rootRelativeFile || entry.file || '').trim().replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/+$/, '');

/** A path as a request names it, in the catalog's spelling: forward slashes, none at either end. */
export const normalizeCatalogPath = (path: string): string => String(path || '').trim().replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/+$/, '');

/** The catalog's entry for a root-relative path, or null. */
export function findCatalogEntry(entries: readonly CadEntry[], path: string): CadEntry | null {
  const wanted = normalizeCatalogPath(path);
  return wanted ? entries.find(entry => catalogPath(entry) === wanted) ?? null : null;
}

/** Render-affecting revisions, not transient compiler progress, invalidate a document. */
export function contentRevision(entry: CadEntry): string {
  return JSON.stringify([entry.hash, entry.documentHash, entry.animationHash, entry.appearanceHash, entry.url, entry.relations, entry.sourceSidecar, entry.mtime, entry.bytes]);
}

const directoriesFirst = (a: FileEntry, b: FileEntry) =>
  Number(b.kind === 'directory') - Number(a.kind === 'directory') || a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });

/**
 * A root's files, read-only, from its CAD catalog. `browse` decides whether they can be browsed:
 * without it the source has no listing, so the viewer shows the one file with no explorer.
 * Catalog changes arrive as the viewer's typed changes: a content change (a new revision) is not
 * a metadata change (compiler progress), so progress never restarts a prepared document.
 */
export function createCatalogFileSource(client: Pick<CadWorkspaceService, 'getSnapshot' | 'subscribe' | 'refresh' | 'resolveEntry'>,
  { id, rootName, browse = true }: { id: string; rootName: string; browse?: boolean }): FileSource {
  const paths = () => client.getSnapshot().entries.map(catalogPath).filter(Boolean);
  async function ready(signal: AbortSignal) {
    signal.throwIfAborted();
    if (!client.getSnapshot().hydrated) await client.refresh({ signal });
    signal.throwIfAborted();
  }
  const source: FileSource = {
    id,
    rootName,
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
  if (!browse) return source;
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

const nativeSeparator = (root: string) => (root.includes('\\') && !root.includes('/') ? '\\' : '/');

/** `relative` (root-relative, forward slashes) under the absolute `root`, in the root's own separator. */
export function rootPath(root: string, relative: string): string {
  const separator = nativeSeparator(root);
  const base = root.replace(/[\\/]+$/, '');
  const tail = normalizeCatalogPath(relative);
  if (!tail) return root;
  return `${base}${separator}${separator === '\\' ? tail.replace(/\//g, '\\') : tail}`;
}

/** An absolute `path` relative to `root`, in forward slashes, or null when it is not under it. */
export function pathUnderRoot(root: string, path: string): string | null {
  const base = root.replace(/\\/g, '/').replace(/\/+$/, '');
  const target = path.replace(/\\/g, '/');
  return target.startsWith(`${base}/`) ? target.slice(base.length + 1) || null : null;
}

/**
 * What a prompt reference names on disk: a URL as it is, a file of this root (`workspaceId`) at
 * its absolute path, in forward slashes — the one spelling a prompt carries in every app, since a
 * backslash path is quoted in the prompt grammar and every host reads forward slashes.
 */
export function referencePath(resource: ResourceRef, { workspaceId, root }: { workspaceId: string; root: string }): string {
  if (resource.kind === 'url') return resource.url;
  if (resource.workspaceId !== workspaceId) throw new Error('This reference belongs to another folder.');
  if (!root) throw new Error('The viewer did not identify its folder.');
  return `${root.replace(/\\/g, '/').replace(/\/+$/, '')}/${normalizeCatalogPath(resource.path)}`;
}

/**
 * The file menu's host actions over a root on this machine: its paths to the clipboard, and the
 * file shown in the desktop's file manager where the host can reveal one. `relative` is whether
 * a path under this root means anything to a person (a folder they serve or work in; not a whole
 * filesystem, where it is the absolute path less its first slash). `root` absent: no absolute
 * paths to copy either.
 */
export function createCadFileActions({ root, platform, clipboard, relative = true, reveal }: {
  root?: string; platform?: string; clipboard: Pick<ClipboardPort, 'writeText'>; relative?: boolean;
  reveal?: (path: string) => Promise<void>;
}): FileActions {
  return {
    platform: platform === 'darwin' || platform === 'win32' || platform === 'linux' ? platform : 'linux',
    perform: {
      ...(root ? { 'copy-path': (entry: { path: string }) => clipboard.writeText(rootPath(root, entry.path)) } : {}),
      ...(relative ? { 'copy-relative-path': (entry: { path: string }) => clipboard.writeText(normalizeCatalogPath(entry.path)) } : {}),
      ...(reveal ? { reveal: (entry: { path: string }) => reveal(entry.path) } : {}),
    },
  };
}
