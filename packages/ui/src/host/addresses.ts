import type { HomeLocation, NavigationTarget } from './types.js';

// What a link, Open in new tab and the search name a document and a project's folder by: the one place each target is
// made, so what names them changes here alone. The host turns a target into its own address (`navigation.hrefOf`).

/** A document, by its id where the host names one, else by its file's path. */
export function documentTarget(document: { id?: string | null; path: string }): NavigationTarget {
  return { document: document.id || document.path };
}

/** A folder of a project, as a place on the home: `path` below the project's root, none or `""` its top. */
export function folderPlace(project: string, path = ''): HomeLocation {
  return { view: 'project', project, ...(path ? { path } : {}) };
}
