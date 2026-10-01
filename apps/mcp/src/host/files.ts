import type { FileSource } from '@text-to-cad/ui/file-viewer';
import { createCatalogFileSource, rootPath } from '@text-to-cad/ui/catalog';
import type { createCadClient } from '@text-to-cad/core/client';
import type { Root } from './server';

export type CadClient = ReturnType<typeof createCadClient>;

/**
 * A model with no project around it, on its own: a whole filesystem's root, whose catalog holds only
 * the file on screen and which nothing lists or walks.
 */
export function createFilesystemSource(client: CadClient, root: Root, { id }: { id: string }): FileSource {
  const catalog = createCatalogFileSource(client, { id, rootName: root.name, browse: false });
  return {
    ...catalog,
    // References name the file absolutely: a path relative to a whole filesystem means nothing outside it.
    referencePath: path => rootPath(root.path, path),
    // A file coming or going in a catalog of the file on screen is another file shown, not the
    // disk changing: only a change to the file that stayed is one.
    subscribe: listener => catalog.subscribe!(change => {
      const changes = change.changes.filter(item => item.kind === 'content' || item.kind === 'metadata');
      if (changes.length) listener({ ...change, changes });
    }),
  };
}
