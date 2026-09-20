import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { FileViewer, type FileViewerState } from '@hardcore/ui/file-viewer';
import type { ViewerHost } from '@hardcore/ui/host';
import { EmptyState } from '@hardcore/ui/navigation';
import { FileText } from 'lucide-react';
import { createCadRenderer } from '@hardcore/ui/renderers/cad';
import { createGlbRenderer } from '@hardcore/ui/renderers/glb';
import { createMeshRenderer } from '@hardcore/ui/renderers/mesh';
import { createRobotRenderer } from '@hardcore/ui/renderers/robot';
import { MissingFileAlert, StatusToast, ViewerLoadingOverlay } from '@hardcore/ui/renderers/cad/presentation';
import { useViewerAutoReload } from './host/useViewerAutoReload.js';
import { EmptyCadBackdrop } from '@hardcore/ui/renderers/cad/empty';
import type { CadServerInfo } from '@hardcore/core/client';
import type { CadClient } from './adapters/fileSource';
import { createWebFileSource, createWebFileActions } from './adapters/fileSource';
import { browserClipboard, browserClipboardSupportsImages } from './host/clipboard';
import { browserLifecycle } from './host/lifecycle';
import { createWebPromptContext } from './host/promptContext';
import { readViewState, restoreCadFileStates, writeViewState } from './persistence/fileViewer';
import { createWebCadPreferences } from './persistence/cadPreferences';
import ViewerTopBar from './client/components/workbench/ViewerTopBar.jsx';
import FilenameLoadStatus from './FilenameLoadStatus';
import { cadFileParamForEntry, findEntryByUrlPath, normalizeCadFileQueryParam, readCadParam, readDefaultCadParam, writeCadParam } from './client/workbench/sidebar.js';
import { applyColorSchemeToDocument, readColorSchemePreference, resolveColorSchemeMode, writeColorSchemePreference } from './client/ui/colorScheme.js';

export default function App(props: { client: CadClient; server: CadServerInfo }) {
  return <RootView key={props.server.rootId} {...props} />;
}

/** A root change creates a new session before any view state can be persisted. */
function RootView({ client, server }: { client: CadClient; server: CadServerInfo }) {
  const [fullscreen, setFullscreen] = useState(false);
  useEffect(() => {
    if (!fullscreen) return;
    const exit = (event: KeyboardEvent) => { if (event.key === "Escape" && !event.defaultPrevented) { event.preventDefault(); setFullscreen(false); } };
    window.addEventListener("keydown", exit);
    return () => window.removeEventListener("keydown", exit);
  }, [fullscreen]);
  const [copyStatus, setCopyStatus] = useState('');
  const viewerReloading = useViewerAutoReload(server, { fetchServerInfo: () => client.serverInfo({ fresh: true }).then(info => ({ ok: true, identityToken: String(info.identityToken || '') }), () => ({ ok: false })) });
  const source = useMemo(() => createWebFileSource(client, server), [client, server]);
  const promptContext = useMemo(() => createWebPromptContext(source.id, server.rootPath || '', browserClipboard, browserClipboardSupportsImages()), [source.id, server.rootPath]);
  const fileActions = useMemo(() => createWebFileActions(client, server, { promptContext, clipboard: browserClipboard, onCopyStatus: setCopyStatus }), [client, server, promptContext]);
  const preferences = useMemo(createWebCadPreferences, []);
  useEffect(() => preferences.connect(), [preferences]);
  // One renderer per file family; each lazy-loads only its own code.
  const renderers = useMemo(() => [createCadRenderer({ client, preferences }), createGlbRenderer({ client, preferences }), createMeshRenderer({ client, preferences }), createRobotRenderer({ client, preferences })], [client, preferences]);
  const catalog = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  const [file, setFile] = useState(() => readCadParam() || readDefaultCadParam() || '');
  const selectedEntry = useMemo(() => findEntryByUrlPath(catalog.entries, file), [catalog.entries, file]);
  const [state, setState] = useState<FileViewerState>(() => readViewState(source.id));
  const publishedState = useRef(state);
  const resolveAppearance = () => ({ colorScheme: resolveColorSchemeMode(readColorSchemePreference(), { prefersDark: matchMedia('(prefers-color-scheme: dark)').matches }) as 'light' | 'dark' });
  const [appearance, setAppearance] = useState(resolveAppearance);
  const [colorSchemePreference, setColorSchemePreference] = useState(readColorSchemePreference);
  const changeColorScheme = useCallback((value: string) => {
    writeColorSchemePreference(value);
    setColorSchemePreference(value);
    setAppearance(resolveAppearance());
  }, []);
  useEffect(() => {
    const query = matchMedia('(prefers-color-scheme: dark)');
    const update = () => { setColorSchemePreference(readColorSchemePreference()); setAppearance(resolveAppearance()); };
    query.addEventListener('change', update); window.addEventListener('storage', update);
    return () => { query.removeEventListener('change', update); window.removeEventListener('storage', update); };
  }, []);
  useEffect(() => { applyColorSchemeToDocument(readColorSchemePreference(), document.documentElement, { prefersDark: matchMedia('(prefers-color-scheme: dark)').matches }); }, [appearance]);
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
    document.title = selectedEntry ? `text-to-cad | ${selectedEntry.file.split(/[\\/]/).pop()}` : 'text-to-cad';
    if (selectedEntry && !readCadParam()) writeCadParam(file, { history: 'replace' });
    setState(previous => restoreCadFileStates(previous, catalog.entries));
  }, [file, catalog.entries, selectedEntry]);
  useEffect(() => {
    writeViewState(source.id, state, sessionStorage, publishedState.current);
    publishedState.current = state;
  }, [state, source.id]);
  const open = useCallback((path: string) => {
    const entry = findEntryByUrlPath(client.getSnapshot().entries, path);
    if (!entry) return;
    const next = normalizeCadFileQueryParam(cadFileParamForEntry(entry));
    writeCadParam(next, { history: 'push' });
    setFile(next);
    // The original compact surface clears the tree after selecting its file.
    if (window.innerWidth < 520) setState(previous => previous.panel === 'tree' || previous.panel === null ? { ...previous, panel: '' } : previous);
  }, [client]);
  const host = useMemo<ViewerHost>(() => ({
    files: source, fileActions, clipboard: browserClipboard, promptContext,
    navigation: { openFile: open }, environment: appearance, lifecycle: browserLifecycle,
  }), [source, fileActions, promptContext, open, appearance]);
  const empty = <div className="pointer-events-auto absolute inset-0 z-10 bg-background"><EmptyState icon={FileText} title="No file open" description="Pick one from the tree on the right, or filter by name." /></div>;
  return <div className="flex h-svh flex-col overflow-hidden"><ViewerTopBar fullscreen={fullscreen} onFullscreenChange={setFullscreen} fullscreenAvailable={Boolean(selectedEntry)} colorSchemePreference={colorSchemePreference} resolvedColorSchemeMode={appearance.colorScheme} onColorSchemePreferenceChange={changeColorScheme} /><div className="min-h-0 flex-1">
    <FileViewer fullscreen={fullscreen} onExitFullscreen={() => setFullscreen(false)} file={file || null} host={host} renderers={renderers} state={state} onStateChange={setState} narrowCrumbs={false}
      navigationPath={selectedEntry ? normalizeCadFileQueryParam(cadFileParamForEntry(selectedEntry)) : null}
      onError={error => setCopyStatus(error.message)} presentation={{
        empty: <div className="relative h-full">{empty}</div>,
        loading: <div className="relative h-full"><ViewerLoadingOverlay viewerLoading /></div>,
        error: () => <div className="relative h-full">{catalog.error ? empty : <EmptyCadBackdrop colorScheme={appearance.colorScheme}><MissingFileAlert missingFileRef={file} rootPath={server.rootPath} /></EmptyCadBackdrop>}</div>,
        activity: activity => <FilenameLoadStatus activity={viewerReloading ? { loading: true, label: "Reloading", title: "The viewer is restarting after a code change." } : activity} />,
      }} />
  </div><StatusToast previewMode={fullscreen} copyStatus={copyStatus} onClear={() => setCopyStatus('')} /></div>;
}
