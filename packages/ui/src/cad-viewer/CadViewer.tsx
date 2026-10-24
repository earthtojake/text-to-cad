import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { ExportControls } from '../export/ExportControls.js';
import { FileWarning } from 'lucide-react';
import type { CadWorkspaceService } from '@text-to-cad/core/client';
import { FileViewer } from '../file-viewer/FileViewer.js';
import { ViewerLoadingOverlay } from '../file-viewer/presentation.js';
import { EmptyState } from '../file-viewer/navigation/index.js';
import { Button } from '../primitives/button.jsx';
import type { AppSetting, ColorSchemeSetting, LanguageSetting, ViewerHistory } from '../file-viewer/types.js';
import { I18nProvider, translator } from '../i18n/index.js';
import type { ViewerHost } from '../host/types.js';
import type { LiveRegistry } from '../host/liveRegistry.js';
import { ModelLibrary, type LibraryModel, type ModelLibrarySource } from '../library/ModelLibrary.js';
import { useModelThumbnail } from '../library/thumbnails.js';
import { OffscreenPicture, cadRenderers, type ModelPictureSource } from './OffscreenPicture.js';
import type { LibraryLayout } from '../tab-store/tabRecord.js';
import type { TabStore } from '../tab-store/tabStore.js';
import { useTabViewerState } from '../tab-store/useTabViewerState.js';
import { normalizePath } from './catalog.js';
import { isDocumentId } from '@text-to-cad/core/lib/cadRefs.js';
import { LaunchFolder } from './LaunchFolder.js';
import { MissingCadFile } from './MissingCadFile.js';

// A STEP: read by the cadgen engine, at a length its size decides (the home's pictures ask first).
const STEP_FILE = /\.(?:step|stp)$/i;

export interface CadViewerProps<Model extends LibraryModel = LibraryModel> {
  /** The CAD client: the catalog of the files on screen, and every document's resources. */
  client: CadWorkspaceService;
  /**
   * The host's ports: its files (`createCadFileSource`), clipboard, prompt destination, file
   * actions, links and environment. Navigation is this component's: it shows a file through `onShow`.
   */
  host: Omit<ViewerHost, 'navigation'>;
  /**
   * The tab's one store: the renderers' preferences, the viewer's state, the home's layout, and the
   * view of the file on screen, the only file view it keeps: leaving a file drops its view.
   */
  tabStore: TabStore;
  /** The host's handle on the mounted view: its agent reads it, and the library's pictures come through it. */
  live: LiveRegistry;
  /** The file on screen, by its absolute path, or a document the engine holds by its id alone (a model's); `''` is none: the home. */
  file: string;
  /** Show another file (absolute), or the home (`''`). */
  onShow(file: string): void;
  /**
   * The file on screen once the catalog has it, or null (the home, or a file still resolving or
   * missing), and its document's id: what the host names it by (`/<id>`).
   */
  onShown?(file: string | null, id: string | null): void;
  /** The folder the home shows under the recent files: the most recent launch's. */
  start?: string;
  /**
   * The home's library: the models opened before, to open again, and Open. A host with one shows it
   * wherever no file is open, and the navbar's logo leads to it from a file. Without one (a host
   * whose own navigation shows one file, as a file handler does) a view has a file and nothing else:
   * no home, no explorer, and no link to another file.
   */
  library?: ModelLibrarySource<Model>;
  /** Keep the library's picture of a model: the file on screen once it has settled, and on the home a card's. */
  onThumbnail?(png: Blob, file: string): Promise<unknown>;
  /** The person's colour scheme, its rows in the app menu over every file and on the home. */
  colorScheme?: ColorSchemeSetting;
  /**
   * The person's language, its row in the app menu over every file and on the home: Automatic
   * (what the context infers) or one they chose. The language in force is the host's `environment.locale`.
   */
  language?: LanguageSetting;
  /** The host's on/off settings, in the app menu the logo opens over every file and on the home (analytics). */
  appSettings?: readonly AppSetting[];
  /** The host's notice: a file's viewport, top-right, once the file is on screen; never the home. */
  notice?: ReactNode;
  /**
   * The host's update button (`@text-to-cad/ui/update`'s `UpdateButton`), while its install is behind:
   * first among the navbar's controls, over every file and on the home.
   */
  update?: ReactNode;
  /**
   * The host's Full size button, where it shows the view small (inline in a conversation) and can
   * show it full size: in the navbar, over every file and on the home, before the view's own controls.
   */
  fullSize?: ReactNode;
  /**
   * The host's way to open what is shown in a page of its own outside the host (the CAD app's Open
   * in browser), where it has one: last in the navbar, over every file and on the home.
   */
  openInBrowser?: ReactNode;
  /**
   * The view's own history, where the host keeps one rather than a browser (the CAD app's views):
   * Back and Forward in the navbar after its logo, over every file and on the home.
   */
  history?: ViewerHistory;
  onError?(error: Error): void;
}

const reportError = (error: Error) => console.error(error);

/**
 * The CAD viewer every app shows: the shared FileViewer over one file at a time, by absolute path,
 * with its six renderers (STEP, DXF, GLB, STL/3MF, URDF/SRDF/SDF, a cadgen engine document), the host's home (the model
 * library) wherever no file is open, and the standard loading and "File does not exist" pages. It
 * follows the catalog of the file on screen and refreshes it when the page is focused or shown
 * again. It keeps a picture of each model it shows for the library (`onThumbnail`), and on the home
 * draws one for a card that has none or an old one: out of sight, with its own client, one model at a
 * time, and only a model whose display is already built — the home never starts a build. It never
 * navigates: showing a file, or the home, is the host's `onShow`.
 */
export function CadViewer<Model extends LibraryModel = LibraryModel>({ client, host, tabStore, live, file, onShow, onShown, start,
  library, onThumbnail, colorScheme, language, appSettings, notice, update, fullSize, openInBrowser, history, onError = reportError }: CadViewerProps<Model>) {
  // The language the host names: the pages drawn here (the home, a file that will not open) read in it.
  const locale = host.environment.locale;
  const t = translator(locale);
  const preferences = tabStore.settings;
  // One viewer renderer per file family, sharing one client and the tab's preferences; each
  // lazy-loads only its own code.
  const renderers = useMemo(() => cadRenderers(client, preferences, live.binding), [client, preferences, live]);
  const catalog = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  const settings = useSyncExternalStore(preferences.subscribe, preferences.getSnapshot, preferences.getSnapshot);
  const { state, onStateChange } = useTabViewerState(tabStore);
  const path = normalizePath(file);
  const latest = useRef({ onShow, onShown, onThumbnail, path, shown: null as string | null });
  latest.current = { onShow, onShown, onThumbnail, path, shown: latest.current.shown };

  // The file on screen once the catalog has it: its row joined by the document's id, so a symlink and
  // its target, or two spellings of one path, are one row (`client.entryOf`).
  const entry = path ? (client.entryOf ? client.entryOf(path) : catalog.entries.find(item => normalizePath(item.file) === path) ?? null) : null;
  // What is on screen by its own name: the file's path, or the id of a document with no file of its
  // own (a model's). `file` may name it either way: a host addresses documents by id.
  const shown = entry ? (entry.sourcePath === null ? path : normalizePath(entry.file)) : null;
  const shownId = entry ? String(entry.id || '') || null : null;
  latest.current.shown = shown;
  useEffect(() => { latest.current.onShown?.(shown, shownId); }, [shown, shownId]);

  // Only the file on screen keeps its view in the tab (`tab-store`): leaving a model — for another
  // file, or for the home — drops its camera, Display settings, pose and the rest, while a reload of
  // the tab (which shows the same file) brings them back, and an update of the model keeps them. The
  // departing renderer writes its view once more as it unmounts; that write is a cleanup of the
  // commit that changed `file`, and every cleanup of a commit runs before its effects, this one
  // included, so it cannot bring the view back. The tab's settings are not a file's, and stay.
  useEffect(() => { tabStore.files.retain(path || null); }, [tabStore, path]);

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
  // A document known by its id alone (a model's) is not in the library: it has no file.
  useModelThumbnail(live, shown && !isDocumentId(shown) ? shown : null, String(entry?.documentHash || entry?.hash || ''),
    (png, pictured) => latest.current.onThumbnail?.(png, pictured) ?? Promise.resolve());

  // A file the viewer asks for — a pick in the explorer, a renderer's link — is shown by the host.
  // A view with no library shows its file and nothing else: it opens no other, and has no home.
  const openFile = useCallback((next: string) => {
    const wanted = normalizePath(next);
    if (wanted && wanted !== latest.current.path && wanted !== latest.current.shown) latest.current.onShow(wanted);
  }, []);
  const homed = Boolean(library);
  const home = useCallback(() => latest.current.onShow(''), []);
  const viewerHost = useMemo<ViewerHost>(() => ({ ...host, navigation: homed ? { openFile, home } : {} }), [host, openFile, home, homed]);

  // The home's pictures for cards without a current one, drawn out of sight one at a time and kept as
  // the file on screen's are. A STEP the cadgen engine does not hold is left to its placeholder: the
  // home never starts the engine's read of one (a large STEP's is long), it only asks.
  const [drawing, setDrawing] = useState<{ source: ModelPictureSource; done(kept: boolean): void } | null>(null);
  const drawable = Boolean(library && onThumbnail);
  const picture = useMemo(() => (drawable ? async (model: Model) => {
    const file = normalizePath(model.path);
    if (latest.current.path || isDocumentId(file)) return false;
    if (STEP_FILE.test(file) && !(await client.engineHolds?.(file).catch(() => false))) return false;
    if (latest.current.path) return false;
    const keep = (png: Blob) => latest.current.onThumbnail?.(png, model.path) ?? Promise.resolve();
    return new Promise<boolean>(done => setDrawing({ source: { client, file, keep }, done }));
  } : undefined), [drawable, client]);
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
  useEffect(() => { if (path) drawn(false); }, [path, drawn]);

  const layout = settings.library.layout;
  const changeLayout = useCallback((next: LibraryLayout) => preferences.update({ library: { layout: next } }), [preferences]);
  // A file that will not open says why, with the way home where the host has one.
  const goHome = useMemo(() => homed ? <Button size="sm" variant="outline" onClick={home}>{t("file.goHome")}</Button> : null, [homed, home, t]);
  const presentation = useMemo(() => ({
    home: library ? <ModelLibrary library={library} layout={layout} onLayoutChange={changeLayout} picture={picture}
      links={host.links} onError={onError}
      after={start && host.files.list ? <LaunchFolder source={host.files} folder={start} onOpen={openFile} /> : null} /> : undefined,
    loading: <div className="relative h-full"><ViewerLoadingOverlay viewerLoading /></div>,
    // A document named by its id that the engine does not hold says why, and the command that
    // builds it again (the engine's words); a file that is not there, its path.
    error: ({ message, missing, reload }: { message: string; missing: boolean; reload?: () => void }) => missing
      ? <MissingCadFile file={path} entry={entry} reload={reload} action={goHome}
        title={isDocumentId(path) ? t("file.notHeld") : t("file.missing")} description={isDocumentId(path) ? message : undefined} />
      : <EmptyState icon={FileWarning} title={t("file.openFailed")} description={message} tone="warn" action={goHome} />,
  }), [library, layout, changeLayout, path, picture, host.links, host.files, openFile, entry, onError, goHome, t, start]);
  return <I18nProvider locale={locale}>
    <ExportControls service={client.exports} downloads={host.downloads} file={shown ?? path}>{({ navbar, overlay }) => <FileViewer navbarActions={navbar} overlay={overlay} file={path || null} host={viewerHost} renderers={renderers} state={state} onStateChange={onStateChange}
      colorScheme={colorScheme} language={language} appSettings={appSettings} update={update} fullSize={fullSize} openInBrowser={openInBrowser} history={history} notice={notice} onError={onError} presentation={presentation} />}</ExportControls>
    {drawing && !path ? <OffscreenPicture key={drawing.source.file} source={drawing.source} host={host} preferences={preferences} onDone={drawn} /> : null}
  </I18nProvider>;
}
