import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { CadViewer, createCatalogFileSource } from '@text-to-cad/ui/cad-viewer';
import { createLiveRegistry, type ViewerHost } from '@text-to-cad/ui/host';
import type { TabStore, Appearance } from '@text-to-cad/ui/tab-store';
import { createHttpAttachmentStore, type CadServerInfo } from '@text-to-cad/core/client';
import type { createCadClient } from '@text-to-cad/core/client';
import { useViewerAutoReload } from './host/useViewerAutoReload.js';
import { createWebFileActions } from './adapters/fileActions';
import { createWebLibrary, recordOpened, recordThumbnail } from './adapters/library';
import { browserClipboard, browserClipboardSupportsImages } from './host/clipboard';
import { createWebPromptContext } from './host/promptContext';
import { useViewerLinks } from './host/viewerLinks.js';
import ViewerAppearance from './client/components/workbench/ViewerAppearance.jsx';
import { normalizeCadFileQueryParam, readCadParam, readDefaultCadParam, writeCadParam } from './client/workbench/sidebar.js';
import { applyColorSchemeToDocument, resolveColorSchemeMode } from './client/ui/colorScheme.js';

export type CadClient = ReturnType<typeof createCadClient>;

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

/** The file the URL names, or this build's default: `?file=` is root-relative. */
const requestedFile = () => readCadParam() || readDefaultCadParam() || '';

export default function App(props: { client: CadClient; server: CadServerInfo; tabStore: TabStore }) {
  return <RootView key={props.server.rootId} {...props} />;
}

/** A root change creates a new session; the tab store, and everything in it, is the tab's across roots. */
function RootView({ client, server, tabStore }: { client: CadClient; server: CadServerInfo; tabStore: TabStore }) {
  useViewerAutoReload(server, { fetchServerInfo: () => client.serverInfo({ fresh: true }).then(info => ({ ok: true, identityToken: String(info.identityToken || '') }), () => ({ ok: false })) });
  // The served folder's catalog, browsed in place.
  const source = useMemo(() => createCatalogFileSource(client, { id: server.rootId, rootName: 'This directory' }), [client, server]);
  const promptContext = useMemo(() => createWebPromptContext(source.id, server.rootPath || '', browserClipboard, browserClipboardSupportsImages()), [source.id, server.rootPath]);
  const fileActions = useMemo(() => createWebFileActions(server, { clipboard: browserClipboard }), [server]);
  // A copied Quick Edit's sketch, saved by the server beside it on this machine.
  const attachments = useMemo(() => createHttpAttachmentStore({ origin: client.origin }), [client]);
  // The view on screen, for the library's pictures of what was opened.
  const live = useMemo(() => createLiveRegistry(), []);
  const links = useViewerLinks();
  const [file, setFile] = useState(requestedFile);
  const appearance = useTabAppearance(tabStore);
  const changeColorScheme = useCallback((value: string) => tabStore.settings.update({ appearance: value as Appearance }), [tabStore]);
  useEffect(() => { applyColorSchemeToDocument(appearance.colorScheme, document.documentElement); }, [appearance.colorScheme]);
  useEffect(() => {
    const sync = () => setFile(requestedFile());
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);
  const shownFile = useRef(file);
  shownFile.current = file;
  /** Show a file by its path, or the home (''), whether or not the catalog has read it yet: the viewer resolves it. */
  const show = useCallback((next: string) => {
    const path = normalizeCadFileQueryParam(next);
    if (path === shownFile.current) return;
    writeCadParam(path, { history: 'push' });
    setFile(path);
  }, []);
  // Once the catalog has the file: the page is named after it, the URL names it (a default file
  // too), and it joins the library every CAD view shares.
  const shown = useCallback((path: string | null) => {
    document.title = path ? `CAD | ${path.split('/').pop()}` : 'CAD';
    if (!path) return;
    if (!readCadParam()) writeCadParam(path, { history: 'replace' });
    void recordOpened(path).catch(() => {});
  }, []);
  const library = useMemo(() => createWebLibrary({ open: show }), [show]);
  const host = useMemo<Omit<ViewerHost, 'navigation'>>(() => ({
    files: source, fileActions, clipboard: browserClipboard, promptContext, attachments, links,
    environment: { colorScheme: appearance.colorScheme, platform: keyboardPlatform() },
  }), [source, fileActions, promptContext, attachments, links, appearance.colorScheme]);
  return <div className="flex h-svh flex-col overflow-hidden"><div className="min-h-0 flex-1">
    <CadViewer client={client} host={host} tabStore={tabStore} live={live} file={file} onShow={show} onShown={shown}
      rootPath={server.rootPath || ''} library={library} onThumbnail={recordThumbnail}
      displayActions={<ViewerAppearance colorSchemePreference={appearance.preference} resolvedColorSchemeMode={appearance.colorScheme} onColorSchemePreferenceChange={changeColorScheme} />} />
  </div></div>;
}
