import { isDocumentId } from './cadRefs.js';

// The viewer's page of a document, as an address in its origin: the one place that spells it and reads it back. A
// host builds every document link from it (the web page's addresses, Copy link), so what names a document in an
// address changes here alone.

/** The path of the page of the document `id` names: `/<id>`. */
export function documentPage(id) {
  return `/${encodeURIComponent(String(id))}`;
}

/** The document a page's path names (`documentPage`'s), or null: any other path is no document's page. */
export function documentOfPage(pathname) {
  const value = String(pathname || '').replace(/^\/+|\/+$/g, '');
  return isDocumentId(value) ? value : null;
}
