import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { FolderX } from 'lucide-react';
import type { CadWorkspaceService } from '@text-to-cad/core/client';
import { FileViewer } from '../file-viewer/FileViewer.js';
import { EmptyCadBackdrop } from '../file-viewer/empty.js';
import { MissingFileAlert, ViewerLoadingOverlay } from '../file-viewer/presentation.js';
import { EmptyState } from '../file-viewer/navigation/index.js';
import type { ViewerHost } from '../host/types.js';
import type { LiveRegistry } from '../host/liveRegistry.js';
import { ModelLibrary, type LibraryModel, type ModelLibrarySource, type ModelPictureSource } from '../library/ModelLibrary.js';
import { useModelThumbnail } from '../library/thumbnails.js';
import { OffscreenPicture, cadRenderers } from './OffscreenPicture.js';
import type { LibraryLayout } from '../tab-store/tabRecord.js';
import type { TabStore } from '../tab-store/tabStore.js';
import { useTabViewerState } from '../tab-store/useTabViewerState.js';
import { catalogPath, findCatalogEntry, normalizeCatalogPath } from './catalog.js';

export interface CadViewerProps<Model extends LibraryModel = LibraryModel> {
  /** The root's CAD client: its catalog, and every document's resources. */
  client: CadWorkspaceService;
  /**
   * The host's ports: the root's files (`createCatalogFileSource`, or a host's own), clipboard,
   * prompt destination, file actions, links and environment. Navigation is this component's: it
   * shows a file through `onShow`.
   */
  host: Omit<ViewerHost, 'navigation'>;
  /** The tab's one store: the renderers' preferences, this root's viewer state, the home's layout. */
  tabStore: TabStore;
  /** The host's handle on the mounted view: its agent reads it, and the library's pictures come through it. */
  live: LiveRegistry;
  /** The file on screen, root-relative; `''` is the home. */
  file: string;
  /** Show another file (root-relative, as `accept` named it), or the home (`''`). */
  onShow(file: string): void;
  /**
   * The file a request to show `path` shows, or null when there is none to show. By default, the
   * entry the catalog lists for it: a root whose catalog holds only the file on screen (a whole
   * filesystem, read a folder at a time) accepts what its explorer lists.
   */
  accept?(path: string): string | null;
  /** The file on screen once the catalog has it, or null (the home, or a file still resolving). */
  onShown?(file: string | null): void;
  /** The root's absolute path, named by a missing file's alert. */
  rootPath: string;
  /** The home's library: the models opened before, to open again. */
  library: ModelLibrarySource<Model>;
  /** Keep the library's picture of the file on screen, once it has settled. */
  onThumbnail?(png: Blob, file: string): Promise<unknown>;
  /** The host's controls in the Display settings (the web's appearance). */
  displayActions?: ReactNode;
  onError?(error: Error): void;
}

const reportError = (error: Error) => console.error(error);

/**
 * The CAD viewer every app shows: the shared FileViewer over one root's CAD catalog, with its five
 * renderers (STEP, DXF, GLB, STL/3MF, URDF/SRDF/SDF), the host's home (the model library) where no
 * file is open, and the standard loading and missing-file pages. It follows the catalog — the file
 * on screen is named once the catalog has it, a missing one once the catalog has answered — and
 * refreshes it when the page is focused or shown again. It keeps a picture of each model it shows
 * for the library, and on the home draws one for a card that has none or an old one, where the
 * host says how (`library.pictureFrom`): out of sight, one model at a time, and only a model whose
 * display is already built — the home never starts a build. It never navigates: showing a file,
 * or the home, is the host's `onShow`.
 *
 * A host supplies what is its own: where the root is and how its catalog is reached (`client`),
 * its ports (`host`), where the tab's state lives (`tabStore`), what shows a file (`onShow`), and
 * its library.
 */
export function CadViewer<Model extends LibraryModel = LibraryModel>({ client, host, tabStore, live, file, onShow, accept, onShown, rootPath,
  library, onThumbnail, displayActions, onError = reportError }: CadViewerProps<Model>) {
  const preferences = tabStore.settings;
  // One viewer renderer per file family, sharing one client and the tab's preferences; each
  // lazy-loads only its own code.
  const renderers = useMemo(() => cadRenderers(client, preferences, live.binding), [client, preferences, live]);
  const catalog = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  const settings = useSyncExternalStore(preferences.subscribe, preferences.getSnapshot, preferences.getSnapshot);
  const { state, onStateChange, setPanel } = useTabViewerState(tabStore, host.files.id);
  const latest = useRef({ onShow, accept, onShown, onThumbnail, file, library });
  latest.current = { onShow, accept, onShown, onThumbnail, file, library };

  // The file on screen once the catalog has it. While the catalog resolves a requested file the
  // navbar names nothing; once it has answered, a missing file is named by its own path.
  const entry = file ? findCatalogEntry(catalog.entries, file) : null;
  const shown = entry ? catalogPath(entry) : null;
  const navigationPath = shown ?? (catalog.hydrated ? normalizeCatalogPath(file) || null : null);
  useEffect(() => { latest.current.onShown?.(shown); }, [shown]);

  // Refresh the catalog when the person comes back to the page: a model may have been rebuilt meanwhile.
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

  // What is on screen joins the library with a picture, once it has settled.
  useModelThumbnail(live, shown, (png, pictured) => latest.current.onThumbnail?.(png, pictured) ?? Promise.resolve());

  // A file the viewer asks for — a pick in the explorer, a renderer's link — is shown by the host,
  // and opens with the panel it was asked for (the explorer, for a pick there) or its own default;
  // the file already on screen keeps what it has open unless a panel is asked for.
  const openFile = useCallback((path: string, options?: { target: 'current' | 'new'; panel?: string }) => {
    const { accept: accepts, onShow: show, file: onScreen } = latest.current;
    const listed = findCatalogEntry(client.getSnapshot().entries, path);
    const next = accepts ? accepts(path) : listed ? catalogPath(listed) : null;
    if (next === null) return;
    if (next !== onScreen) show(next);
    else if (options?.panel === undefined) return;
    setPanel(options?.panel ?? null);
  }, [client, setPanel]);
  const home = useCallback(() => latest.current.onShow(''), []);
  const viewerHost = useMemo<ViewerHost>(() => ({ ...host, navigation: { openFile, home } }), [host, openFile, home]);

  // The home's pictures for cards without a current one, drawn out of sight one at a time. A model
  // whose display is not built yet is left to its placeholder: the status is read, never built.
  const [drawing, setDrawing] = useState<{ source: ModelPictureSource; done(kept: boolean): void } | null>(null);
  const drawable = Boolean(library.pictureFrom);
  const picture = useMemo(() => (drawable ? async (model: Model) => {
    const source = latest.current.library.pictureFrom?.(model);
    if (!source || latest.current.file) return false;
    const status = await source.client.requestArtifactStatus(source.file).catch(() => null);
    if (status?.state !== 'compiled' || latest.current.file) return false;
    return new Promise<boolean>(done => setDrawing({ source, done }));
  } : undefined), [drawable]);
  const inFlight = useRef(drawing);
  inFlight.current = drawing;
  const drawn = useCallback((kept: boolean) => {
    const picturing = inFlight.current;
    if (!picturing) return;
    inFlight.current = null;
    setDrawing(null);
    picturing.done(kept);
  }, []);
  // A file opened meanwhile has the screen, and the GPU, to itself.
  useEffect(() => { if (file) drawn(false); }, [file, drawn]);

  const colorScheme = host.environment.colorScheme;
  const layout = settings.library.layout;
  const changeLayout = useCallback((next: LibraryLayout) => preferences.update({ library: { layout: next } }), [preferences]);
  const presentation = useMemo(() => ({
    home: <ModelLibrary library={library} layout={layout} onLayoutChange={changeLayout} picture={picture} />,
    loading: <div className="relative h-full"><ViewerLoadingOverlay viewerLoading /></div>,
    error: () => <div className="relative h-full">{catalog.error
      ? <EmptyState icon={FolderX} title="Could not read this folder" description={catalog.error} tone="warn" />
      : <EmptyCadBackdrop colorScheme={colorScheme}><MissingFileAlert missingFileRef={file} rootPath={rootPath} /></EmptyCadBackdrop>}</div>,
  }), [library, colorScheme, layout, changeLayout, catalog.error, file, rootPath, picture]);
  return <>
    <FileViewer file={file || null} host={viewerHost} renderers={renderers} state={state} onStateChange={onStateChange}
      displayActions={displayActions} navigationPath={navigationPath} onError={onError} presentation={presentation} />
    {drawing && !file ? <OffscreenPicture key={drawing.source.file} source={drawing.source} host={host} preferences={preferences} onDone={drawn} /> : null}
  </>;
}
