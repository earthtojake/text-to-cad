import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { FileViewer, type FileViewerState } from '@hardcore/ui/file-viewer';
import { EmptyState } from '@hardcore/ui/navigation';
import { FileText } from 'lucide-react';
import { createCadRenderer } from '@hardcore/ui/renderers/cad';
import { MissingFileAlert, StatusToast, ViewerLoadingOverlay } from '@hardcore/ui/renderers/cad/presentation';
import { EmptyCadBackdrop } from '@hardcore/ui/renderers/cad/empty';
import type { CadServerInfo } from '@hardcore/core/client';
import type { CadClient } from './adapters/fileSource';
import { createWebFileSource } from './adapters/fileSource';
import { readViewState, restoreCadFileStates, writeViewState } from './persistence/fileViewer';
import { createWebCadPreferences } from './persistence/cadPreferences';
import ViewerTopBar from './client/components/workbench/ViewerTopBar.jsx';
import FilenameLoadStatus from './FilenameLoadStatus';
import { cadFileParamForEntry, findEntryByUrlPath, normalizeCadFileQueryParam, readCadParam, readDefaultCadParam, writeCadParam } from './client/workbench/sidebar.js';
import { applyColorSchemeToDocument, readColorSchemePreference, resolveColorSchemeMode } from './client/ui/colorScheme.js';

export default function App(props: { client: CadClient; server: CadServerInfo }) {
  return <RootView key={props.server.rootId} {...props} />;
}

/** A root change creates a new session before any view state can be persisted. */
function RootView({ client, server }: { client: CadClient; server: CadServerInfo }) {
  const [copyStatus, setCopyStatus] = useState('');
  const source = useMemo(() => createWebFileSource(client, server, { onCopyStatus: setCopyStatus }), [client, server]);
  const preferences = useMemo(createWebCadPreferences, []);
  useEffect(() => preferences.connect(), [preferences]);
  const renderers = useMemo(() => [createCadRenderer({ client, preferences })], [client, preferences]);
  const catalog = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  const [file, setFile] = useState(() => readCadParam() || readDefaultCadParam() || '');
  const selectedEntry = useMemo(() => findEntryByUrlPath(catalog.entries, file), [catalog.entries, file]);
  const [state, setState] = useState<FileViewerState>(() => readViewState(source.id));
  const resolveAppearance = () => ({ colorScheme: resolveColorSchemeMode(readColorSchemePreference(), { prefersDark: matchMedia('(prefers-color-scheme: dark)').matches }) as 'light' | 'dark' });
  const [appearance, setAppearance] = useState(resolveAppearance);
  useEffect(() => {
    const query = matchMedia('(prefers-color-scheme: dark)');
    const update = () => setAppearance(resolveAppearance());
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
  useEffect(() => { writeViewState(source.id, state); }, [state, source.id]);
  const open = useCallback((path: string) => {
    const entry = findEntryByUrlPath(client.getSnapshot().entries, path);
    if (!entry) return;
    const next = normalizeCadFileQueryParam(cadFileParamForEntry(entry));
    writeCadParam(next, { history: 'push' });
    setFile(next);
    // The original compact surface clears the tree after selecting its file.
    if (window.innerWidth < 520) setState(previous => previous.panel === 'tree' || previous.panel === null ? { ...previous, panel: '' } : previous);
  }, [client]);
  const empty = <div className="pointer-events-auto absolute inset-0 z-10 bg-background"><EmptyState icon={FileText} title="No file open" description="Pick one from the tree on the right, or filter by name." /></div>;
  return <div className="flex h-svh flex-col overflow-hidden"><ViewerTopBar /><div className="min-h-0 flex-1">
    <FileViewer file={file || null} source={source} renderers={renderers} state={state} onStateChange={setState} onOpenFile={open} appearance={appearance} narrowCrumbs={false}
      navigationPath={selectedEntry ? normalizeCadFileQueryParam(cadFileParamForEntry(selectedEntry)) : null}
      onError={error => setCopyStatus(error.message)} presentation={{
        empty: <div className="relative h-full">{empty}</div>,
        loading: <div className="relative h-full"><ViewerLoadingOverlay viewerLoading /></div>,
        error: () => <div className="relative h-full">{catalog.error ? empty : <EmptyCadBackdrop preferences={preferences} colorScheme={appearance.colorScheme}><MissingFileAlert missingFileRef={file} rootPath={server.rootPath} /></EmptyCadBackdrop>}</div>,
        activity: activity => <FilenameLoadStatus activity={activity} />,
      }} />
  </div><StatusToast copyStatus={copyStatus} onClear={() => setCopyStatus('')} /></div>;
}
