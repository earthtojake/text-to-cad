import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { FileViewer } from '@text-to-cad/ui/file-viewer';
import type { ViewerHost } from '@text-to-cad/ui/host';
import { EmptyState } from '@text-to-cad/ui/navigation';
import { FileText } from 'lucide-react';
import { createStepRenderer } from '@text-to-cad/ui/renderers/step';
import { createDxfRenderer } from '@text-to-cad/ui/renderers/dxf';
import { createGlbRenderer } from '@text-to-cad/ui/renderers/glb';
import { createMeshRenderer } from '@text-to-cad/ui/renderers/mesh';
import { createRobotRenderer } from '@text-to-cad/ui/renderers/robot';
import { MissingFileAlert, ViewerLoadingOverlay } from '@text-to-cad/ui/file-viewer/presentation';
import { useTabViewerState, type Appearance, type TabStore } from '@text-to-cad/ui/tab-store';
import { useViewerAutoReload } from './host/useViewerAutoReload.js';
import { EmptyCadBackdrop } from '@text-to-cad/ui/file-viewer/empty';
import type { CadServerInfo } from '@text-to-cad/core/client';
import type { CadClient } from './adapters/fileSource';
import { createWebFileSource, createWebFileActions } from './adapters/fileSource';
import { browserClipboard, browserClipboardSupportsImages } from './host/clipboard';
import { createWebPromptContext } from './host/promptContext';
import ViewerAppearance from './client/components/workbench/ViewerAppearance.jsx';
import ViewerBrand from './client/components/workbench/ViewerBrand.jsx';
import ViewerLinks from './client/components/workbench/ViewerLinks.jsx';
import { cadFileParamForEntry, findEntryByUrlPath, normalizeCadFileQueryParam, readCadParam, readDefaultCadParam, writeCadParam } from './client/workbench/sidebar.js';
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

export default function App(props: { client: CadClient; server: CadServerInfo; tabStore: TabStore }) {
  return <RootView key={props.server.rootId} {...props} />;
}

/** A root change creates a new session; the tab store, and everything in it, is the tab's across roots. */
function RootView({ client, server, tabStore }: { client: CadClient; server: CadServerInfo; tabStore: TabStore }) {
  useViewerAutoReload(server, { fetchServerInfo: () => client.serverInfo({ fresh: true }).then(info => ({ ok: true, identityToken: String(info.identityToken || '') }), () => ({ ok: false })) });
  const source = useMemo(() => createWebFileSource(client, server), [client, server]);
  const promptContext = useMemo(() => createWebPromptContext(source.id, server.rootPath || '', browserClipboard, browserClipboardSupportsImages()), [source.id, server.rootPath]);
  const fileActions = useMemo(() => createWebFileActions(client, server, { clipboard: browserClipboard }), [client, server]);
  // Every renderer reads its preferences from the tab's settings.
  const preferences = tabStore.settings;
  // One renderer per file family; each lazy-loads only its own code.
  const renderers = useMemo(() => [createStepRenderer({ client, preferences }), createDxfRenderer({ client, preferences }), createGlbRenderer({ client, preferences }), createMeshRenderer({ client, preferences }), createRobotRenderer({ client, preferences })], [client, preferences]);
  const catalog = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  const [file, setFile] = useState(() => readCadParam() || readDefaultCadParam() || '');
  const selectedEntry = useMemo(() => findEntryByUrlPath(catalog.entries, file), [catalog.entries, file]);
  // The FileViewer's state, from and into the tab store: the panel column's width, this root's open
  // folders and its file views. The open panel is the page's own and never stored.
  const { state, onStateChange, setPanel } = useTabViewerState(tabStore, source.id);
  const appearance = useTabAppearance(tabStore);
  const changeColorScheme = useCallback((value: string) => tabStore.settings.update({ appearance: value as Appearance }), [tabStore]);
  useEffect(() => { applyColorSchemeToDocument(appearance.colorScheme, document.documentElement); }, [appearance.colorScheme]);
  useEffect(() => {
    const sync = () => setFile(readCadParam() || readDefaultCadParam() || '');
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => { void client.refresh({ signal: controller.signal, markRefreshing: false }).catch(() => {}); };
    const visible = () => { if (document.visibilityState !== 'hidden') refresh(); };
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', visible);
    return () => {
      controller.abort();
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [client]);
  useEffect(() => {
    document.title = selectedEntry ? `CAD | ${selectedEntry.file.split(/[\\/]/).pop()}` : 'CAD';
    if (selectedEntry && !readCadParam()) writeCadParam(file, { history: 'replace' });
  }, [file, selectedEntry]);
  const shownFile = useRef(file);
  shownFile.current = file;
  const open = useCallback((path: string, options?: { panel?: string }) => {
    const entry = findEntryByUrlPath(client.getSnapshot().entries, path);
    if (!entry) return;
    const next = normalizeCadFileQueryParam(cadFileParamForEntry(entry));
    if (next !== shownFile.current) {
      writeCadParam(next, { history: 'push' });
      setFile(next);
    } else if (options?.panel === undefined) return;
    // The file opens with the panel it was opened with (the tree, for one picked there) or with
    // its own default. FileViewer owns mobile visibility and keeps its sheets closed.
    setPanel(options?.panel ?? null);
  }, [client, setPanel]);
  const host = useMemo<ViewerHost>(() => ({
    files: source, fileActions, clipboard: browserClipboard, promptContext,
    navigation: { openFile: open }, environment: { colorScheme: appearance.colorScheme, platform: keyboardPlatform() },
  }), [source, fileActions, promptContext, open, appearance.colorScheme]);
  const empty = <div className="pointer-events-auto absolute inset-0 z-10 bg-background"><EmptyState icon={FileText} title="No file open" description="Pick one from the tree on the right, or filter by name." /></div>;
  // Unselected while the catalog resolves the file; once it has, a missing file is named by its own crumbs.
  const navigationPath = selectedEntry ? normalizeCadFileQueryParam(cadFileParamForEntry(selectedEntry)) : catalog.hydrated ? normalizeCadFileQueryParam(file) || null : null;
  return <div className="flex h-svh flex-col overflow-hidden"><div className="min-h-0 flex-1">
    <FileViewer file={file || null} host={host} renderers={renderers} state={state} onStateChange={onStateChange}
      // The app names itself wherever no crumbs do: no file, or one still resolving.
      leading={<ViewerBrand />} navigationActions={<ViewerLinks />}
      displayActions={<ViewerAppearance colorSchemePreference={appearance.preference} resolvedColorSchemeMode={appearance.colorScheme} onColorSchemePreferenceChange={changeColorScheme} />}
      navigationPath={navigationPath}
      onError={error => console.error(error)} presentation={{
        empty: <div className="relative h-full">{empty}</div>,
        loading: <div className="relative h-full"><ViewerLoadingOverlay viewerLoading /></div>,
        error: () => <div className="relative h-full">{catalog.error ? empty : <EmptyCadBackdrop colorScheme={appearance.colorScheme}><MissingFileAlert missingFileRef={file} rootPath={server.rootPath} /></EmptyCadBackdrop>}</div>,
      }} />
  </div></div>;
}
