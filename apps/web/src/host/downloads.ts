import type { DownloadPort, ExportRecord } from '@text-to-cad/ui/host';

function tabStorage(): Storage | undefined {
  try { return window.sessionStorage; } catch { return undefined; }
}

/**
 * The plain web download: a same-origin link with `download`, clicked. The browser's own
 * download behaviour (its folder, or its Save dialog where the person asked for one) decides
 * where the file goes, in every browser. The session cookie authenticates the URL, so no token
 * is in it. Tab storage keeps the exports still under way across a reload, never a file.
 */
export function createBrowserDownloads({ document: page = window.document, storage = tabStorage(),
  key = `cadgen:exporting:${window.location.pathname}` }: {
  document?: Pick<Document, 'createElement' | 'body'>; storage?: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>; key?: string;
} = {}): DownloadPort {
  return {
    save(url, filename) {
      const link = page.createElement('a');
      link.href = url;
      link.download = filename;
      link.rel = 'noopener';
      link.hidden = true;
      page.body.append(link);
      try { link.click(); } finally { link.remove(); }
    },
    restore() {
      try {
        const value = JSON.parse(storage?.getItem(key) || '[]');
        return Array.isArray(value) ? value.filter((row): row is ExportRecord => typeof row?.filename === 'string'
          && typeof row.request?.requestId === 'string' && typeof row.request?.epoch === 'string' && Boolean(row.request?.source))
          .map(({ request, filename }) => ({ request, filename })) : [];
      } catch { return []; }
    },
    remember(value) {
      try { if (value.length) storage?.setItem(key, JSON.stringify(value)); else storage?.removeItem(key); } catch { /* tab storage may be unavailable */ }
    },
  };
}
