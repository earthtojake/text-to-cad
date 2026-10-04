import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { CadViewer, createCadFileSource, normalizePath } from '@text-to-cad/ui/cad-viewer';
import type { ModelLibrarySource } from '@text-to-cad/ui/library';
import { createLiveRegistry, type ViewerHost } from '@text-to-cad/ui/host';
import type { TabStore, Appearance } from '@text-to-cad/ui/tab-store';
import { createHttpAttachmentStore, type CadServerInfo } from '@text-to-cad/core/client';
import type { createCadClient } from '@text-to-cad/core/client';
import { useViewerAutoReload } from './host/useViewerAutoReload.js';
import { createWebFileActions } from './adapters/fileActions';
import { changeRecents, listRecents, pickModel, recordOpened, recordThumbnail, thumbnailUrl } from './adapters/library';
import { consent as analyticsConsent, reportActivity } from './adapters/analytics';
import { features as viewerFeatures } from './adapters/features';
import { version } from './adapters/version';
import { ConsentCard, useAnalyticsConsent } from '@text-to-cad/ui/consent';
import { useFeatures } from '@text-to-cad/ui/features';
import { UpdateButton, useUpdateNotice, type UpdateNotice } from '@text-to-cad/ui/update';
import { browserClipboard, browserClipboardSupportsImages } from './host/clipboard';
import { createWebPromptContext } from './host/promptContext';
import { useViewerLinks } from './host/viewerLinks.js';
import ViewerAppearance from './client/components/workbench/ViewerAppearance.jsx';
import { readDefaultFileParam, readFileParam, resolveFileParam, writeFileParam } from './client/workbench/fileParam.js';
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

/**
 * The CAD Viewer's page: one file at a time, by the absolute path its URL names (`?file=`), or the
 * home — the models opened before, and Open — where it names none. The browser's own history is
 * the way back: showing a file or the home is a new entry.
 */
export default function App({ client, server, tabStore, notice = null }: { client: CadClient; server: CadServerInfo; tabStore: TabStore; notice?: UpdateNotice | null }) {
  useViewerAutoReload(server, { fetchServerInfo: () => client.serverInfo({ fresh: true }).then(info => ({ ok: true, identityToken: String(info.identityToken || '') }), () => ({ ok: false })) });
  const source = useMemo(() => createCadFileSource(client), [client]);
  const promptContext = useMemo(() => createWebPromptContext(browserClipboard, browserClipboardSupportsImages()), []);
  const fileActions = useMemo(() => createWebFileActions(server, { clipboard: browserClipboard }), [server]);
  // A copied Quick Edit's sketch, saved by the server beside it on this machine.
  const attachments = useMemo(() => createHttpAttachmentStore({ origin: client.origin }), [client]);
  // The view on screen, for the library's pictures of what was opened.
  const live = useMemo(() => createLiveRegistry(), []);
  const links = useViewerLinks();
  // The file the URL names (a developer's relative path resolved where this viewer started), or the
  // build's default; the URL then names it in full.
  const requested = useCallback(() => resolveFileParam(readFileParam() || readDefaultFileParam() || '', server.start), [server.start]);
  const [file, setFile] = useState(requested);
  useEffect(() => { if (file && readFileParam() !== file) writeFileParam(file, { history: 'replace' }); }, []);
  useEffect(() => {
    const sync = () => setFile(requested());
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, [requested]);
  const shownFile = useRef(file);
  shownFile.current = file;
  /** Show a file by its absolute path, or the home (''): a new step in the browser's history. */
  const show = useCallback((next: string) => {
    const path = normalizePath(next);
    if (path === shownFile.current) return;
    writeFileParam(path, { history: 'push' });
    setFile(path);
  }, []);
  // Once the catalog has the file: the page is named after it, and it joins the library every CAD view shares.
  const shown = useCallback((path: string | null) => {
    document.title = path ? `CAD | ${path.split('/').pop()}` : 'CAD';
    if (!path) return;
    void recordOpened(path).catch(() => {});
    reportActivity({ file: path });
  }, []);
  // The home: the library every CAD view shares, and Open with the desktop's chooser where the
  // server's computer has one. A card without a picture has its model drawn out of sight.
  const library = useMemo<ModelLibrarySource>(() => ({
    list: listRecents,
    change: (action, entry) => changeRecents({ action, path: entry.path }),
    thumbnail: name => Promise.resolve(thumbnailUrl(name)),
    open: async entry => { show(entry.path); },
    ...(server.pick ? { pick: async () => { const picked = await pickModel(); if (picked) show(picked); } } : {}),
    pictureFrom: entry => ({ client, file: normalizePath(entry.path), keep: png => recordThumbnail(png, entry.path) }),
  }), [client, server.pick, show]);
  const appearance = useTabAppearance(tabStore);
  const changeColorScheme = useCallback((value: string) => tabStore.settings.update({ appearance: value as Appearance }), [tabStore]);
  useEffect(() => { applyColorSchemeToDocument(appearance.colorScheme, document.documentElement); }, [appearance.colorScheme]);
  // CAD's anonymous usage analytics, the same as the CAD app's: one card, asked once of everyone
  // (unless their environment answered, or no answer could be kept) once a model is on screen, and
  // the app menu's toggle after it. The answer is the person's, shared with the CAD app.
  const { consent, answer, appSettings: analyticsSettings } = useAnalyticsConsent(analyticsConsent);
  // The app menu's features (Quick edit), on until the person turns one off: kept by this Viewer's
  // server beside the analytics answer, one choice with the CAD app's, whatever port this is.
  const { features, appSettings: featureSettings } = useFeatures(viewerFeatures);
  const appSettings = useMemo(() => [...analyticsSettings ?? [], ...featureSettings ?? []], [analyticsSettings, featureSettings]);
  // A newer text-to-cad, as the CAD app says it (`cadgen/updates.py`): the blue update button, first
  // in the navbar and a row of its own on the home while this install is behind, from the notice read
  // with the server's description (`main.tsx`). A page in a browser cannot reach the agent's chat, so
  // its prompt is copied.
  const updateNotice = useUpdateNotice(version, notice);
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
      library={library} onThumbnail={recordThumbnail} appSettings={appSettings} features={features}
      notice={consent?.ask ? <ConsentCard policy={consent.policy} onAnswer={answer} onPolicy={openTab} /> : null}
      update={updateNotice ? <UpdateButton notice={updateNotice} copy={prompt => browserClipboard.writeText(prompt)} onLink={openTab} /> : null}
      displayActions={<ViewerAppearance colorSchemePreference={appearance.preference} resolvedColorSchemeMode={appearance.colorScheme} onColorSchemePreferenceChange={changeColorScheme} />} />
  </div></div>;
}
