import { useEffect, useState } from 'react';
import type { FileEntry, FileSource } from '../file-viewer/types.js';
import { FileIcon, FolderIcon } from '../file-viewer/navigation/icons.jsx';
import { useI18n } from '../i18n/index.js';
import { baseName, normalizePath } from './catalog.js';

/**
 * The home's folder of the most recent launch (`cadgen viewer`, which each launch replaces): its
 * subfolders and CAD files, read through the host's files. A file opens; a subfolder is listed in
 * its place, the launch folder's name leading back. Nothing is drawn until the folder is read, and
 * nothing for a folder that cannot be read.
 */
export function LaunchFolder({ source, folder, onOpen }: { source: Pick<FileSource, 'list'>; folder: string; onOpen(path: string): void }) {
  const { t } = useI18n();
  const root = normalizePath(folder);
  const [at, setAt] = useState(root);
  useEffect(() => { setAt(root); }, [root]);
  const [listing, setListing] = useState<{ folder: string; entries: readonly FileEntry[] } | null>(null);
  useEffect(() => {
    if (!source.list || !at) return undefined;
    const controller = new AbortController();
    source.list(at, { signal: controller.signal }).then(
      entries => { if (!controller.signal.aborted) setListing({ folder: at, entries }); },
      () => { if (!controller.signal.aborted) setListing(null); });
    return () => controller.abort();
  }, [source, at]);
  if (!listing || listing.folder !== at) return null;
  const folders = listing.entries.filter(entry => entry.kind === 'directory');
  const files = listing.entries.filter(entry => entry.kind !== 'directory');
  return <section className="cad-library-folder" aria-label={t('home.launchFolder')} data-folder={at}>
    <div className="cad-library-toolbar">
      <h2 className="cad-library-heading">{t('home.launchFolder')}</h2>
      <p className="cad-library-status" title={at}>
        {at !== root ? <><button type="button" className="cad-library-crumb" onClick={() => setAt(root)}>{baseName(root)}</button> / </> : null}
        {baseName(at)}
      </p>
    </div>
    {folders.length || files.length ? <ul className="cad-library-list">
      {[...folders, ...files].map(entry => <li key={entry.path} className="cad-library-row">
        <button type="button" className="cad-library-open" data-kind={entry.kind}
          onClick={() => (entry.kind === 'directory' ? setAt(normalizePath(entry.path)) : onOpen(entry.path))}>
          {entry.kind === 'directory' ? <FolderIcon open={false} className="size-4 shrink-0" /> : <FileIcon path={entry.path} className="size-4 shrink-0" />}
          <span className="cad-library-name">{entry.name}</span>
        </button>
      </li>)}
    </ul> : <p className="cad-library-status">{t('explorer.noCadFilesHere')}</p>}
  </section>;
}
