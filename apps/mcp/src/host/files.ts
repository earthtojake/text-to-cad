import type { FileEntry, FileSource } from '@text-to-cad/ui/file-viewer';
import { createCatalogFileSource } from '@text-to-cad/ui/catalog';
import type { createCadClient } from '@text-to-cad/core/client';
import type { Root } from './server';
import { TUNNEL_ORIGIN } from './tunnel';

export type CadClient = ReturnType<typeof createCadClient>;

const directoriesFirst = (a: FileEntry, b: FileEntry) =>
  Number(b.kind === 'directory') - Number(a.kind === 'directory') || a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });

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
  const catalog = createCatalogFileSource(client, { id, rootName: root.name, browse: false });
  const source: FileSource = {
    ...catalog,
    // References name the file absolutely: a path relative to a whole filesystem means nothing outside it.
    referencePath: path => absolutePath(root, path),
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
