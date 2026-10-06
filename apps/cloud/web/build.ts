/**
 * A build's addresses, pure: the page at `/b/<build>/<virtual path>` shows one of the build's
 * files, the build's viewer API answers under `/b/<build>/__cad/*`, and a file's address — what a
 * copied reference, a Quick Edit and Copy link name it by — is the page's own URL for it.
 */

export interface BuildLocation {
  /** The build's id: one path segment, never `__cad` or `__tess_cache`. */
  id: string;
  /** The file the page shows, as a virtual path (`/STEP/a.step`), or '' when the link names none. */
  path: string;
}

const ID = /^[A-Za-z0-9][A-Za-z0-9_-]*$/;

/** The one spelling of a virtual path: forward slashes, one leading slash, no trailing one, decoded. */
export function normalizeVirtualPath(path: string): string {
  const parts = String(path || '').replace(/\\/g, '/').split('/').filter(part => part && part !== '.');
  return parts.length ? `/${parts.join('/')}` : '';
}

/** What a page's pathname names: the build and its file. Null for a pathname that is no build's. */
export function parseBuildLocation(pathname: string): BuildLocation | null {
  const match = /^\/b\/([^/]+)(\/.*)?$/.exec(String(pathname || ''));
  if (!match) return null;
  let id: string;
  try { id = decodeURIComponent(match[1]); } catch { return null; }
  if (!ID.test(id) || id.startsWith('__')) return null;
  let rest = match[2] || '';
  try { rest = decodeURIComponent(rest); } catch { return null; }
  if (/^\/__(?:cad|tess_cache)(?:\/|$)/.test(rest)) return null;
  return { id, path: normalizeVirtualPath(rest) };
}

/** The page's path for a file of the build: `/b/<build>/STEP/a.step`, each segment encoded. */
export function buildPagePath(id: string, path: string): string {
  const virtual = normalizeVirtualPath(path);
  return `/b/${encodeURIComponent(id)}${virtual.split('/').map(part => encodeURIComponent(part)).join('/')}`;
}

/** The build's viewer API origin, for `createCadClient`: `<page origin>/b/<build>`, absolute. */
export function buildOrigin(pageOrigin: string, id: string): string {
  return `${String(pageOrigin || '').replace(/\/+$/, '')}/b/${encodeURIComponent(id)}`;
}

/** The address a file of the build is named by: its page's URL. */
export function fileAddress(pageOrigin: string, id: string, path: string): string {
  return `${String(pageOrigin || '').replace(/\/+$/, '')}${buildPagePath(id, path)}`;
}

/** The file's name: the last part of its virtual path. */
export function baseName(path: string): string {
  const normal = normalizeVirtualPath(path);
  return normal.slice(normal.lastIndexOf('/') + 1);
}
