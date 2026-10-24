import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { CadViewer, createCadFileSource, normalizePath } from '@text-to-cad/ui/cad-viewer';
import { createCadFileActions } from '@text-to-cad/ui/catalog';
import type { ModelLibrarySource } from '@text-to-cad/ui/library';
import { createLiveRegistry, type ViewerHost } from '@text-to-cad/ui/host';
import type { TabStore, Appearance } from '@text-to-cad/ui/tab-store';
import { cadApiUrl, createHttpPromptFiles, type CadClient, type CadServerInfo } from '@text-to-cad/core/client';
import { useViewerAutoReload } from './host/useViewerAutoReload.js';
import { useAnalyticsConsent } from '@text-to-cad/ui/consent';
import { useLanguage } from '@text-to-cad/ui/i18n';
import { UpdateButton, useUpdateNotice, type UpdateNotice } from '@text-to-cad/ui/update';
import { createBrowserDownloads } from './host/downloads';
import { browserClipboard, browserClipboardSupportsImages } from './host/clipboard';
import { createWebPromptContext } from './host/promptContext';
import { useViewerLinks } from './host/viewerLinks.js';
import { EngineStopped } from './EngineStopped';
import { readDefaultFileParam, readDocumentId, writeDocumentId } from './client/workbench/fileParam.js';
import { applyColorSchemeToDocument, resolveColorSchemeMode } from './client/ui/colorScheme.js';

/** The keyboard the page is typed on — ⌘ on Apple devices, Ctrl elsewhere: the host's one platform answer. */
const keyboardPlatform = () => /Mac|iPhone|iPad/.test(navigator.platform) ? "darwin" : /Win/.test(navigator.platform) ? "win32" : "linux";
// A card's link (the privacy policy, the full install instructions): a new tab, as the navbar's open.
const openTab = (url: string) => { window.open(url, '_blank', 'noopener,noreferrer'); };
const DARK_QUERY = '(prefers-color-scheme: dark)';
const subscribeToSystemDark = (onChange: () => void) => {
  const query = matchMedia(DARK_QUERY);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
};
const systemPrefersDark = () => matchMedia(DARK_QUERY).matches;

/** The appearance the tab keeps, resolved against the OS: `light` or `dark`, live. */
export function useTabAppearance(tabStore: TabStore): { preference: Appearance; colorScheme: 'light' | 'dark' } {
  const settings = useSyncExternalStore(tabStore.settings.subscribe, tabStore.settings.getSnapshot, tabStore.settings.getSnapshot);
  const prefersDark = useSyncExternalStore(subscribeToSystemDark, systemPrefersDark, systemPrefersDark);
  return { preference: settings.appearance, colorScheme: resolveColorSchemeMode(settings.appearance, { prefersDark }) as 'light' | 'dark' };
}

const DOCUMENT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/**
 * The CAD Viewer's page: one document at a time, by the id its URL's path names (`/<id>`: a model's,
 * or a file's, which the server registers when it is opened), or the home (`/`) — the models opened
 * before, Open, and the folder of the most recent launch. A file opened by its path (Select File, the
 * home) is asked for its id first, and shown by it. The browser's own history is the way back:
 * showing a document or the home is a new entry.
 */
export default function App({ client, server, tabStore, notice = null, language: chosenLanguage = null }: { client: CadClient; server: CadServerInfo; tabStore: TabStore; notice?: UpdateNotice | null; language?: string | null }) {
  // Another process answering on this page's port: never loaded into the tab (a dev server's restart
  // alone is followed), and said as the engine being gone.
  const [foreign, setForeign] = useState(false);
  useViewerAutoReload(server, { fetchServerInfo: () => client.serverInfo({ fresh: true }).then(info => ({ ok: true, identityToken: String(info.identityToken || '') }), () => ({ ok: false })),
    follow: Boolean(import.meta.env?.DEV), onForeign: () => setForeign(true) });
  const downloads = useMemo(() => createBrowserDownloads(), []);
  const source = useMemo(() => createCadFileSource(client), [client]);
  const promptContext = useMemo(() => createWebPromptContext(browserClipboard, browserClipboardSupportsImages()), []);
  // The file menu: the file's path to the clipboard, and Reveal in the file manager of the machine the
  // server runs on, labeled for its platform.
  const fileActions = useMemo(() => createCadFileActions({ platform: server.platform, clipboard: browserClipboard,
    reveal: path => client.reveal(path) }), [server.platform, client]);
  // A copied Quick Edit's annotation, saved by the server beside it on this machine.
  const promptFiles = useMemo(() => createHttpPromptFiles({ origin: client.origin }), [client]);
  // The view on screen, for the library's pictures of what was opened.
  const live = useMemo(() => createLiveRegistry(), []);
  const links = useViewerLinks();
  // The document the URL names; anything else is the home (an old link's form included), and the
  // URL says `/`.
  const [file, setFile] = useState(() => readDocumentId() || '');
  const shownFile = useRef(file);
  shownFile.current = file;
  const asked = useRef(0);
  /** Show a document by its id, a file by its absolute path (asked for its id), or the home (''): a
   * new step in the browser's history, or this one's place (`history: 'replace'`). */
  const show = useCallback(async (next: string, history: 'push' | 'replace' = 'push') => {
    const turn = ++asked.current;
    const wanted = normalizePath(next);
    let id = !wanted || DOCUMENT_ID.test(wanted) ? wanted : '';
    if (wanted && !id) {
      id = await client.resolveEntry(wanted).then(entry => String(entry.id || ''), () => '');
      if (turn !== asked.current) return;
      if (!id) { setFile(wanted); return; }  // a file that is not there says so, by its path
    }
    if (id === shownFile.current) return;
    writeDocumentId(id, { history });
    setFile(id);
  }, [client]);
  useEffect(() => {
    if (!file) {
      writeDocumentId('', { history: 'replace' });
      const fallback = readDefaultFileParam();  // a developer's build's default file
      if (fallback) void show(fallback, 'replace');
    }
    const sync = () => { asked.current += 1; setFile(readDocumentId() || ''); };
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);
  // Once the catalog has the document: the page is named after it, and a file joins the library every
  // CAD view shares (counted, as a code, for analytics). A model, known by its id alone, does not.
  const shown = useCallback((path: string | null) => {
    const entry = path ? client.entryOf?.(path) : null;
    document.title = path ? `CAD | ${entry?.name || path.split('/').pop()}` : 'CAD';
    if (path && !DOCUMENT_ID.test(path)) void client.changeRecents({ action: 'open', path }).catch(() => {});
  }, [client]);
  // The folder of the most recent launch, which the home shows: read again each time the home is.
  const [start, setStart] = useState(server.start || '');
  useEffect(() => {
    if (file) return undefined;
    const controller = new AbortController();
    void client.serverInfo({ fresh: true, signal: controller.signal }).then(info => setStart(String(info.start || '')), () => {});
    return () => controller.abort();
  }, [client, file]);
  // The home: the library every CAD view shares, and Open with the desktop's chooser where the
  // server's computer has one. A card's picture is the server's, by name.
  const library = useMemo<ModelLibrarySource>(() => ({
    list: () => client.recents(),
    change: (action, entry) => client.changeRecents({ action, path: entry.path }),
    thumbnail: name => Promise.resolve(cadApiUrl('/__cad/thumbnail', { origin: client.origin, params: { name } })),
    open: async entry => { await show(entry.path); },
    ...(server.pick ? { pick: async () => { const picked = await client.pick(); if (picked) await show(picked); } } : {}),
  }), [client, server.pick, show]);
  const appearance = useTabAppearance(tabStore);
  const changeColorScheme = useCallback((value: string) => tabStore.settings.update({ appearance: value as Appearance }), [tabStore]);
  // The app menu's Theme row, over every file and on the home.
  const colorScheme = useMemo(() => ({ preference: appearance.preference, onPreferenceChange: changeColorScheme }), [appearance.preference, changeColorScheme]);
  useEffect(() => { applyColorSchemeToDocument(appearance.colorScheme, document.documentElement); }, [appearance.colorScheme]);
  // The person's language: inferred from the browser's languages until they choose one in the app menu,
  // which their settings keep for every CAD view (`useLanguage`); read with the server's description
  // (`main.tsx`), so the page's first paint is already in it.
  const { locale, language } = useLanguage(client.language, { preferred: navigator.languages ?? [navigator.language], initial: chosenLanguage });
  useEffect(() => { document.documentElement.lang = locale; }, [locale]);
  // The usage stats cadgen sends (its telemetry), the same as the CAD app's: nothing asks here (a
  // cadgen command says it once), and the app menu's switch changes it. The answer is the person's,
  // shared with the CAD app.
  const { appSettings } = useAnalyticsConsent(client.consent, locale);
  // A newer text-to-cad, as the CAD app says it (`cadgen/updates.py`): the blue update button, first
  // in the navbar and a row of its own on the home while this install is behind, from the notice read
  // with the server's description (`main.tsx`). A page in a browser cannot reach the agent's chat, so
  // its prompt is copied.
  const updateNotice = useUpdateNotice(client.version, notice);
  // A person touching the page is use (time spent looking at a model makes no other request): said
  // at most every couple of seconds.
  useEffect(() => {
    let last = 0;
    const touched = () => {
      if (Date.now() - last < 2000) return;
      last = Date.now();
      client.reportActivity({ touched: true });
    };
    window.addEventListener('pointerdown', touched, true);
    window.addEventListener('keydown', touched, true);
    return () => { window.removeEventListener('pointerdown', touched, true); window.removeEventListener('keydown', touched, true); };
  }, [client]);
  const host = useMemo<Omit<ViewerHost, 'navigation'>>(() => ({
    downloads, files: source, fileActions, clipboard: browserClipboard, promptContext, promptFiles, links,
    // A Quick Edit copied, counted by this Viewer's server for its telemetry, as a touch is.
    usage: { used: feature => { if (feature === 'quickEdit') client.reportActivity({ quickEdit: true }); } },
    environment: { colorScheme: appearance.colorScheme, locale, platform: keyboardPlatform() },
  }), [downloads, client, source, fileActions, promptContext, promptFiles, links, appearance.colorScheme, locale]);
  // The engine gone under the page: said over it, which stays as it was for the engine's return.
  const engineGone = useSyncExternalStore(client.subscribe, () => client.getSnapshot().engineGone, () => false) || foreign;
  return <div className="relative flex h-svh flex-col overflow-hidden">{engineGone ? <EngineStopped locale={locale} /> : null}<div className="min-h-0 flex-1">
    <CadViewer client={client} host={host} tabStore={tabStore} live={live} file={file} onShow={next => { void show(next); }} onShown={shown} start={start}
      library={library} onThumbnail={client.keepThumbnail} appSettings={appSettings}
      update={updateNotice ? <UpdateButton notice={updateNotice} copy={prompt => browserClipboard.writeText(prompt)} onLink={openTab} /> : null}
      colorScheme={colorScheme} language={language} />
  </div></div>;
}
