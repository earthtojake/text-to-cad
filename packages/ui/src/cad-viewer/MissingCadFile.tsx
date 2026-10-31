import { useEffect, useRef, type ReactNode } from 'react';
import { FileX } from 'lucide-react';
import type { CadEntry } from '@text-to-cad/core/client';
import { EmptyState } from '../file-viewer/navigation/index.js';
import { useI18n } from '../i18n/index.js';

/** A file that is not there (yet). When the catalog has it -- a build wrote it, or it was put back --
 * the view opens it, once for each version of it: `reload` is the host's. Nothing else is watched:
 * a document the cadgen engine builds is written whole, and the engine says nothing of a build
 * before it is. `title` is the host's translation of "File does not exist", else the surrounding
 * language's. */
export function MissingCadFile({ file, entry, reload, action, title, description }: {
  file: string; entry: CadEntry | null; reload?: () => void; action?: ReactNode; title?: string;
  /** What to say in place of the file's path: why a document named by its id is not held. */
  description?: string;
}) {
  const { t } = useI18n();
  const reloaded = useRef('');
  useEffect(() => {
    // Reopen only once the catalog confirms a file at this very path: a stale entry or another
    // file's late reply cannot do it.
    const identity = entry?.file === file ? `${file}:${entry.hash || ''}:${entry.bytes || 0}` : '';
    if (identity && reload && reloaded.current !== identity) {
      reloaded.current = identity;
      reload();
    }
  }, [file, entry, reload]);
  return <EmptyState icon={FileX} title={title ?? t("file.missing")} description={description ?? file} tone="warn" action={action} />;
}
