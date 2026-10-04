import type { CadEntry, CadWorkspaceService } from '@text-to-cad/core/client';
import type { ClipboardPort } from '../host/types.js';
import type { FileActions, FileMetadata, FileSource } from '../file-viewer/types.js';

/**
 * `@text-to-cad/ui/catalog`: CAD files as the viewer reads them, by absolute path. Pure — no React
 * and no transport — so a host's adapters and their unit tests import it alone.
 *
 * A view shows one file and browses from its folder. The source a host hands the viewer
 * (`createCadFileSource`) reads the file's catalog entry, lists a folder at a time and searches
 * under one, all through a CAD client; the file menu (`createCadFileActions`) copies a file's
 * path and reveals it. Every path is absolute, in forward slashes, in every app.
 */

/** `path` in the viewer's one spelling: forward slashes, and no trailing one but the top's (`/`, `C:/`). */
export function normalizePath(path: string): string {
  const slashed = String(path || '').trim().replace(/\\/g, '/');
  const trimmed = slashed.replace(/\/+$/, '');
  return trimmed === '' ? (slashed ? '/' : '') : /^[A-Za-z]:$/.test(trimmed) ? `${trimmed}/` : trimmed;
}

/** The last part of `path`: a file's name. */
export function baseName(path: string): string {
  const normal = normalizePath(path);
  return normal.slice(normal.lastIndexOf('/') + 1) || normal;
}

/** `name` inside the folder `folder`. */
export function joinPath(folder: string, name: string): string {
  const base = normalizePath(folder);
  return base.endsWith('/') ? `${base}${name}` : `${base}/${name}`;
}

/** Render-affecting revisions, not transient compiler progress, invalidate a document. */
export function contentRevision(entry: CadEntry): string {
  return JSON.stringify([entry.hash, entry.documentHash, entry.animationHash, entry.appearanceHash, entry.url, entry.relations, entry.sourceSidecar, entry.mtime, entry.bytes]);
}

/**
 * The files a view reads, through a CAD client: a file's metadata from its catalog entry, one
 * folder's subfolders and CAD files, and a bounded search under a folder. A file's revision is its
 * content's (`contentRevision`), never compiler progress. (A renderer follows its file's updates
 * through the client itself.)
 */
export function createCadFileSource(client: Pick<CadWorkspaceService, 'resolveEntry' | 'folder' | 'search'>,
  { id = 'local' }: { id?: string } = {}): FileSource {
  return {
    id,
    async stat(path, { signal }): Promise<FileMetadata> {
      const entry = await client.resolveEntry(path, { signal });
      signal.throwIfAborted();
      const file = normalizePath(entry.file);
      const name = baseName(file);
      return { path: file, name, kind: 'file', size: Number(entry.bytes || 0), extension: name.split('.').pop()?.toLowerCase() || '', mediaType: 'cad', revision: contentRevision(entry) };
    },
    async list(directory, { signal }) {
      const folder = await client.folder(directory, { signal });
      return folder.entries.map(entry => ({ path: joinPath(folder.path, entry.name), name: entry.name, kind: entry.kind }));
    },
    async search(directory, query, { signal }) {
      const found = await client.search(directory, query, { signal });
      return { paths: found.results.map(normalizePath), truncated: found.truncated };
    },
  };
}

/**
 * The file menu's host actions for a file on this machine: its path to the clipboard, and the
 * file shown in the desktop's file manager where the host can reveal one.
 */
export function createCadFileActions({ platform, clipboard, reveal }: {
  platform?: string; clipboard: Pick<ClipboardPort, 'writeText'>; reveal?: (path: string) => Promise<void>;
}): FileActions {
  return {
    platform: platform === 'darwin' || platform === 'win32' || platform === 'linux' ? platform : 'linux',
    perform: {
      'copy-path': (entry: { path: string }) => clipboard.writeText(normalizePath(entry.path)),
      ...(reveal ? { reveal: (entry: { path: string }) => reveal(normalizePath(entry.path)) } : {}),
    },
  };
}
