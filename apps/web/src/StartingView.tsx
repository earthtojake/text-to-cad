import { useMemo, useSyncExternalStore } from 'react';
import { isEngineGone, isEngineRefused } from '@cad/core/client';
import { FileViewer } from '@cad/ui/file-viewer';
import { LoadingStep, ViewerLoadingOverlay } from '@cad/ui/file-viewer/presentation';
import { EmptyState } from '@cad/ui/navigation';
import { I18nProvider, resolveLocale, translateIn } from '@cad/ui/i18n';
import type { TabStore } from '@cad/ui/tab-store';
import { readDocumentId } from './client/workbench/fileParam.js';
import { EngineStopped } from './EngineStopped';
import { useViewerLinks } from './host/viewerLinks.js';

// While the page asks the server what it is (`main.tsx`), its own files are not known: a source whose every question
// never answers keeps the file viewer in its opening phase, and asks the server nothing. It lists and searches, and the
// page has Copy link, as the app's do, so the navbar draws the name's menu and the ⋯ where the app draws them.
const PENDING = () => new Promise<never>(() => {});
const PENDING_FILES = { id: 'starting', stat: PENDING, list: PENDING, search: PENDING };
const NOTHING = () => {};
const FILE_ACTIONS = { perform: { 'copy-link': NOTHING } };

/**
 * What the page shows while it asks the server what it is, and if the server does not answer. Asking, it is the app's
 * own frame as the app's first frame draws it — the real file viewer (`FileViewer`), in its opening phase: the navbar
 * at its height with its border, the panel's toggle where it will be, the logo, the name's place empty with its menu
 * and the ⋯ beside it; for a document's page the panel's stand-in, open where the file's kept choice and the page's
 * width say, and the loading indicator centred under the navbar on the tab's viewport Background — so nothing appears
 * or moves as the app takes over. The home's address gets the home's navbar (its logo where the home's is) over the
 * page's background, with the one indicator. It is inert (nothing in it can be pressed yet) and asks nothing: what it
 * reads is the URL, this build's links and this tab's store. No word it shows depends on the person's language, which
 * comes with the server's description: its words are aria labels and the loading line the page showed before it.
 */
export function StartingView({ error, tabStore }: { error?: Error; tabStore: TabStore }) {
  // Before the server answers there is no kept choice to read: the browser's language.
  const locale = resolveLocale(navigator.languages ?? [navigator.language]);
  const record = useSyncExternalStore(tabStore.subscribe, tabStore.getSnapshot, tabStore.getSnapshot);
  const file = useMemo(() => readDocumentId(), []);
  // The app's links, which are this build's (no request): the navbar draws its logo where the app's does.
  const links = useViewerLinks();
  const host = useMemo(() => ({ files: PENDING_FILES, navigation: { openFile: NOTHING, home: NOTHING }, fileActions: FILE_ACTIONS, links,
    environment: { locale } }), [locale, links]);
  const presentation = useMemo(() => ({
    // A document's: the cover the app's opening phase draws, on the tab's viewport Background.
    loading: <div className="relative h-full"><ViewerLoadingOverlay viewerLoading background={record.settings.viewportBackground} /></div>,
    // The home's: the page's own background, as the library's is, and the one indicator in the app's theme.
    home: <div className="flex h-full items-center justify-center bg-background px-4" data-starting-home="">
      <LoadingStep label={translateIn(locale, 'loading.preparingView')} /></div>,
  }), [record.settings.viewportBackground, locale]);
  if (error) return <I18nProvider locale={locale}><div className="fixed inset-0 overflow-hidden bg-background">{isEngineGone(error)
    ? <EngineStopped locale={locale} refused={isEngineRefused(error)} />
    : <EmptyState title={translateIn(locale, 'app.start.notAnswering')} description={error.message} />}</div></I18nProvider>;
  return <div className="fixed inset-0 flex flex-col overflow-hidden" inert data-starting-view="">
    <div className="isolate min-h-0 flex-1">
      <FileViewer file={file} host={host as never} renderers={[]} state={{ renderers: record.files }} onStateChange={NOTHING}
        explorerFolder="/" presentation={presentation} />
    </div>
  </div>;
}
