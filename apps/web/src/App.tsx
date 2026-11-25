import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { CadViewer, createCadFileSource, normalizePath, type CadViewerProps } from '@cad/ui/cad-viewer';
import { createCadFileActions } from '@cad/ui/catalog';
import type { ModelLibrarySource } from '@cad/ui/library';
import { createLiveRegistry, type HomeLocation, type NavigationTarget } from '@cad/ui/host';
import { samePlace } from '@cad/ui/library';
import type { TabStore, Appearance } from '@cad/ui/tab-store';
import { createHttpPromptFiles, isEngineRefused, type CadClient, type CadServerInfo } from '@cad/core/client';
import { useViewerAutoReload } from './host/useViewerAutoReload.js';
import { useEngineReconnect } from './host/useEngineReconnect.js';
import { reloadWhenClean } from './host/reloadWhenClean.js';
import { useAnalyticsConsent } from '@cad/ui/consent';
import { english, translator, useLanguage } from '@cad/ui/i18n';
import { useWhatsNew } from '@cad/ui/whats-new';
import { createBrowserDownloads } from './host/downloads';
import { createNewTabOpener } from './host/newTab.js';
import { browserClipboard, browserClipboardSupportsImages } from './host/clipboard';
import { createWebPromptContext } from './host/promptContext';
import { useViewerLinks } from './host/viewerLinks.js';
import { EngineStopped } from './EngineStopped';
import { pageAddress, readDefaultFileParam, readDocumentId, readHomePlace, writeDocumentId } from './client/workbench/fileParam.js';
import { applyColorSchemeToDocument, resolveColorSchemeMode } from './client/ui/colorScheme.js';

/** The keyboard the page is typed on — ⌘ on Apple devices, Ctrl elsewhere: the host's one platform answer. */
const keyboardPlatform = () => /Mac|iPhone|iPad/.test(navigator.platform) ? "darwin" : /Win/.test(navigator.platform) ? "win32" : "linux";
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
const RECENTS: HomeLocation = { view: 'recents' };

/**
 * The viewer's page: one document at a time, by the id its URL's path names (`/<id>`: a model's,
 * or a file's, which the server registers when it is opened), or the home (`/`) at the place its query names
 * (`fileParam.js`: Recents, `?view=pinned`, `?view=standalone`, `?project=<id>&path=<folder>`). A file opened by its path (from the
 * home's Open) is asked for its id first, and shown by it. The browser's own history is the way back: showing a
 * document, the home or another place on it is a new entry, and every one of them has its own address, for a link
 * and for Open in new tab.
 */
export default function App({ client, server, tabStore, language: chosenLanguage = null }: { client: CadClient; server: CadServerInfo; tabStore: TabStore; language?: string | null }) {
  // Another process answering on this page's port: never loaded into the tab (a dev server's restart
  // alone is followed), and said as the engine being gone.
  const [foreign, setForeign] = useState(false);
  useViewerAutoReload(server, { fetchServerInfo: () => client.serverInfo({ fresh: true }).then(info => ({ ok: true,
    identityToken: String(info.identityToken || '') }), () => ({ ok: false })),
    follow: Boolean(import.meta.env?.DEV), onForeign: () => setForeign(true), reload: () => { reloadWhenClean(() => window.location.reload()); } });
  const downloads = useMemo(() => createBrowserDownloads(), []);
  const source = useMemo(() => createCadFileSource(client), [client]);
  // What the clipboard port says to the person, in the view's language as it is when it speaks.
  const sayRef = useRef<(key: string, params?: Record<string, unknown>) => string>(english);
  const promptContext = useMemo(() => createWebPromptContext(browserClipboard, browserClipboardSupportsImages(),
    (key, params) => sayRef.current(key, params)), []);
  // The file menu: the file's path to the clipboard, Reveal in the file manager of the machine the
  // server runs on, labeled for its platform, Copy link, and Open in's apps there (the server's own table).
  const fileActions = useMemo(() => createCadFileActions({ platform: server.platform, clipboard: browserClipboard,
    reveal: path => client.reveal(path), openIn: client,
    // Copy link: this page's own origin, and a fresh link from the server.
    link: { origin: () => window.location.origin, client } }), [server.platform, client]);
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
  // The place of the home the URL names: the home's own when it is on screen, and where it opens from a document.
  const [place, setPlace] = useState<HomeLocation>(() => readHomePlace());
  const shownPlace = useRef(place);
  shownPlace.current = place;
  const asked = useRef(0);
  /** Show a document by its id, a file by its absolute path (asked for its id), or the home ('') at a place on it
   * (`place`; Recents with none): a new step in the browser's history, or this one's place (`history: 'replace'`). */
  const show = useCallback(async (next: string, { place: where = RECENTS, history = 'push' }: { place?: HomeLocation; history?: 'push' | 'replace' } = {}) => {
    const turn = ++asked.current;
    const wanted = normalizePath(next);
    let id = !wanted || DOCUMENT_ID.test(wanted) ? wanted : '';
    if (wanted && !id) {
      id = await client.resolveEntry(wanted).then(entry => String(entry.id || ''), () => '');
      if (turn !== asked.current) return;
      if (!id) { setFile(wanted); return; }  // a file that is not there says so, by its path
    }
    if (id === shownFile.current && (id || samePlace(where, shownPlace.current))) return;
    writeDocumentId(id, { history, place: where });
    setFile(id);
    if (!id) setPlace(where);
  }, [client]);
  useEffect(() => {
    if (!file) {
      writeDocumentId('', { history: 'replace', place });
      const fallback = readDefaultFileParam();  // a developer's build's default file
      if (fallback) void show(fallback, { history: 'replace' });
    }
    // Back and Forward: the document, or the place on the home, the address now names.
    const sync = () => {
      asked.current += 1;
      setFile(readDocumentId() || '');
      setPlace(previous => { const named = readHomePlace(); return samePlace(named, previous) ? previous : named; });
    };
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);
  // The document's name, never its id: the catalog's row of it (which the boot asks for with the
  // server's description, `main.tsx`, so a document's page has it from its first frame where the server
  // answers in time), else the name it had when it was shown before or on the home's card it was
  // opened from; else none yet, its place in the navbar empty until the catalog answers. A file
  // opened by its path and not found is named by its path's last segment.
  const names = useRef(new Map<string, string>());
  const catalogName = useSyncExternalStore(client.subscribe,
    () => String((file ? client.entryOf?.(normalizePath(file)) : null)?.name || ''), () => '');
  if (file && catalogName) names.current.set(file, catalogName);
  const name = catalogName || names.current.get(file) || '';
  // The file the catalog has on screen, by its own path (a model's document by its id): `onShown`.
  const [shownPath, setShownPath] = useState<string | null>(null);
  // The place of the home on screen, as the home names it ("Recents", a project's name): `onHomeShown`.
  const [homeName, setHomeName] = useState('');
  // The page is named after it alone ("bracket.step", "juno"; a file with no name of its own, after its
  // path's last segment); the home after its place ("Recents · text-to-cad", "gearbox · text-to-cad"), so a tab of
  // each tells them apart; a document whose name is not known yet, or the home before it has said, is "text-to-cad".
  useEffect(() => {
    const fileName = (path: string | null) => (path && !DOCUMENT_ID.test(path) ? normalizePath(path).split('/').pop() || '' : '');
    document.title = file ? name || fileName(shownPath) || fileName(file) || 'text-to-cad' : homeName ? `${homeName} · text-to-cad` : 'text-to-cad';
  }, [name, shownPath, file, homeName]);
  // Once the catalog has the document, the library every CAD view
  // shares says it was opened now: a file joins it (counted, as a code, for analytics), and a model,
  // known by its id alone and in it since its run, has its opened time.
  const shown = useCallback((path: string | null) => {
    setShownPath(path);
    if (path) void client.changeRecents({ action: 'open', path }).catch(() => {});
  }, [client]);
  // The home: the projects (a project's page is one folder of it, read from the server) and the library every CAD view
  // shares, and Import with the desktop's chooser where the server's computer has one -- a file, shown, or a folder,
  // opened as a project. A card's picture is the server's, by its token.
  const library = useMemo<ModelLibrarySource>(() => ({
    list: () => client.recents(),
    change: (action, entry) => client.changeRecents({ action, path: entry.path }),
    thumbnail: model => Promise.resolve(client.thumbnailUrl(model)),
    open: async entry => {
      // The card's name is the document's until the catalog says it.
      for (const key of [entry.id, normalizePath(entry.path)]) if (key && entry.name) names.current.set(key, entry.name);
      await show(entry.path);
    },
    projects: () => client.projects?.() ?? Promise.resolve([]),
    ...(client.projectFolder ? { folder: (project: string, options: { path?: string; q?: string }) => client.projectFolder!(project, options) } : {}),
    removeProject: project => client.removeProject?.(project.id) ?? Promise.resolve([]),
    ...(server.pick ? {
      pick: async () => { const picked = await client.pick(); if (picked) await show(picked); },
      importFolder: async (start?: string) => {
        const folder = await client.pick({ folder: true, start });
        if (!folder || !client.openProject) return null;
        return { ...await client.openProject(folder), folder };
      },
    } : {}),
  }), [client, server.pick, show]);
  const appearance = useTabAppearance(tabStore);
  const changeColorScheme = useCallback((value: string) => tabStore.settings.update({ appearance: value as Appearance }), [tabStore]);
  // The app menu's Theme row (the menu Settings' cog opens, in the sidebar's foot).
  const colorScheme = useMemo(() => ({ preference: appearance.preference, onPreferenceChange: changeColorScheme }), [appearance.preference, changeColorScheme]);
  useEffect(() => { applyColorSchemeToDocument(appearance.colorScheme, document.documentElement); }, [appearance.colorScheme]);
  // The person's language: inferred from the browser's languages until they choose one in the app menu,
  // which their settings keep for every CAD view (`useLanguage`); read with the server's description
  // (`main.tsx`), so the page's first paint is already in it.
  const { locale, language } = useLanguage(client.language, { preferred: navigator.languages ?? [navigator.language], initial: chosenLanguage });
  useEffect(() => { document.documentElement.lang = locale; }, [locale]);
  sayRef.current = translator(locale);
  // The usage stats text-to-cad sends (its telemetry), the same as the CAD app's: nothing asks here (a
  // cad command says it once), and the app menu's switch changes it. The answer is the person's,
  // shared with the CAD app.
  const { appSettings } = useAnalyticsConsent(client.consent, locale);
  // What's new: once after a release with notes is installed, over the home or a file's view, kept
  // seen in the person's settings for every CAD view (`@cad/ui/whats-new`).
  const whatsNew = useWhatsNew(client.whatsNew);
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
  // What the page alone knows of navigation: every document and every place of the home has an address of its own in
  // this origin (`pageAddress`: a document's by its id; one named by a path has none, and is asked for its id as it
  // is opened), which the session cookie admits in a new tab as it admits a download; and Open in new tab, a tab of
  // this browser.
  const navigation = useMemo(() => {
    const hrefOf = (target: NavigationTarget) => 'document' in target
      ? (DOCUMENT_ID.test(target.document) ? pageAddress({ id: target.document }) : null) : pageAddress({ place: target.home });
    return { hrefOf, openBeside: { kind: 'tab' as const, open: createNewTabOpener({ hrefOf,
      resolve: path => client.resolveEntry(normalizePath(path)).then(entry => String(entry.id || '')) }) } };
  }, [client]);
  const host = useMemo<CadViewerProps['host']>(() => ({
    downloads, files: source, fileActions, clipboard: browserClipboard, promptContext, promptFiles, links, navigation,
    // A Quick Edit copied, counted by this Viewer's server for its telemetry, as a touch is.
    usage: { used: feature => { if (feature === 'quickEdit') client.reportActivity({ quickEdit: true }); },
      // The controls a person used, and how long a tool was up, counted by the shared viewer.
      controls: counts => client.reportActivity({ controls: counts }) },
    environment: { colorScheme: appearance.colorScheme, locale, platform: keyboardPlatform() },
  }), [downloads, client, source, fileActions, promptContext, promptFiles, links, navigation, appearance.colorScheme, locale]);
  // The engine gone under the page: said over it, which stays as it was for the engine's return.
  const engineGone = useSyncExternalStore(client.subscribe, () => client.getSnapshot().engineGone, () => false) || foreign;
  const readRefused = useSyncExternalStore(client.subscribe, () => client.getSnapshot().engineRefused, () => false);
  // Asked again, at the same address with the same token, until an engine answers: a new one reloads the page.
  // An engine that refuses the token runs: the page's link was replaced, which the last ask says once it has asked.
  const askedRefused = useEngineReconnect(engineGone, { instance: server.instance,
    reload: () => { reloadWhenClean(() => window.location.reload()); },
    ask: () => client.serverInfo({ fresh: true }).then(info => info, error => (isEngineRefused(error) ? { refused: true } : null)) });
  const refused = askedRefused ?? readRefused;
  return <div className="fixed inset-0 flex flex-col overflow-hidden">{engineGone ? <EngineStopped locale={locale} refused={refused} /> : null}
    {/* The engine gone, its notice is the page's one: what is under it (a view's own "can't reach"
        card among it) is out of reach and unheard until it is back, and out of sight: the page is a stacking
        context of its own (`isolate`), so no layer of a view's (its tool strip and Quick Edit's bar stand at
        `z-50`, over the view's panels) paints over the notice. The view stays mounted under it, as it was. */}
    <div className="isolate min-h-0 flex-1" inert={engineGone || undefined} aria-hidden={engineGone || undefined}>
    <CadViewer client={client} host={host} tabStore={tabStore} live={live} file={file} name={name} onShown={shown}
      onShow={(next, where) => { void show(next, { place: where }); }} place={place} onHomeShown={(_place, shownAs) => setHomeName(shownAs)}
      library={library} onThumbnail={client.keepThumbnail} appSettings={appSettings}
      colorScheme={colorScheme} language={language}
      whatsNew={engineGone ? undefined : { entry: whatsNew.entry, onDismiss: whatsNew.dismiss }} />
  </div></div>;
}
