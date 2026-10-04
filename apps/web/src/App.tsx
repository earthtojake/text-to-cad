import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { CadViewer, createCatalogFileSource } from '@text-to-cad/ui/cad-viewer';
import { createLiveRegistry, type ViewerHost } from '@text-to-cad/ui/host';
import type { TabStore, Appearance } from '@text-to-cad/ui/tab-store';
import { createHttpAttachmentStore, type CadServerInfo } from '@text-to-cad/core/client';
import type { createCadClient } from '@text-to-cad/core/client';
import { useViewerAutoReload } from './host/useViewerAutoReload.js';
import { createWebFileActions } from './adapters/fileActions';
import { recordOpened, recordThumbnail } from './adapters/library';
import { consent as analyticsConsent, reportActivity } from './adapters/analytics';
import { features as viewerFeatures } from './adapters/features';
import { version } from './adapters/version';
import { ConsentCard, useAnalyticsConsent } from '@text-to-cad/ui/consent';
import { useFeatures } from '@text-to-cad/ui/features';
import { UpdateCard, useUpdateNotice } from '@text-to-cad/ui/update';
import { browserClipboard, browserClipboardSupportsImages } from './host/clipboard';
import { createWebPromptContext } from './host/promptContext';
import { useViewerLinks } from './host/viewerLinks.js';
import ViewerAppearance from './client/components/workbench/ViewerAppearance.jsx';
import { normalizeCadFileQueryParam, readCadParam, readDefaultCadParam, writeCadParam } from './client/workbench/sidebar.js';
import { applyColorSchemeToDocument, resolveColorSchemeMode } from './client/ui/colorScheme.js';

export type CadClient = ReturnType<typeof createCadClient>;

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
  /** Show a file by its path ('' is none), whether or not the catalog has read it yet: the viewer resolves it. */
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
    reportActivity({ file: path });
  }, []);
  // CAD's anonymous usage analytics, the same as the CAD app's: one card, asked once of everyone
  // (unless their environment answered, or no answer could be kept) once a model is on screen, and
  // Settings' Analytics section after it. The answer is the person's, shared with the CAD app.
  const { consent, answer, appSettings: analyticsSettings } = useAnalyticsConsent(analyticsConsent);
  // Settings' Features (Quick edit), on until the person turns one off: kept by this Viewer's
  // server beside the analytics answer, one choice with the CAD app's, whatever port this is.
  const { features, appSettings: featureSettings } = useFeatures(viewerFeatures);
  const appSettings = useMemo(() => [...analyticsSettings ?? [], ...featureSettings ?? []], [analyticsSettings, featureSettings]);
  // A newer text-to-cad, once per release and after that card, as the CAD app says it
  // (`cadgen/updates.py`): a page in a browser cannot reach the agent's chat, so its prompt is copied.
  const update = useUpdateNotice(version);
  // A person touching the page is use (time spent looking at a model makes no other request): said
  // at most every couple of seconds.
  useEffect(() => {
    let last = 0;
    const touched = () => {
      if (Date.now() - last < 2000) return;
      last = Date.now();
      reportActivity({ touched: true });
    };
    window.addEventListener('pointerdown', touched, true);
    window.addEventListener('keydown', touched, true);
    return () => { window.removeEventListener('pointerdown', touched, true); window.removeEventListener('keydown', touched, true); };
  }, []);
  const host = useMemo<Omit<ViewerHost, 'navigation'>>(() => ({
    files: source, fileActions, clipboard: browserClipboard, promptContext, attachments, links,
    environment: { colorScheme: appearance.colorScheme, platform: keyboardPlatform() },
  }), [source, fileActions, promptContext, attachments, links, appearance.colorScheme]);
  return <div className="flex h-svh flex-col overflow-hidden"><div className="min-h-0 flex-1">
    <CadViewer client={client} host={host} tabStore={tabStore} live={live} file={file} onShow={show} onShown={shown}
      rootPath={server.rootPath || ''} onThumbnail={recordThumbnail} appSettings={appSettings} features={features}
      notice={consent?.ask ? <ConsentCard policy={consent.policy} onAnswer={answer} onPolicy={openTab} />
        : update.notice ? <UpdateCard notice={update.notice} copy={prompt => browserClipboard.writeText(prompt)}
          onLink={openTab} onAnswer={update.answer} onClose={update.close} /> : null}
      displayActions={<ViewerAppearance colorSchemePreference={appearance.preference} resolvedColorSchemeMode={appearance.colorScheme} onColorSchemePreferenceChange={changeColorScheme} />} />
  </div></div>;
}
