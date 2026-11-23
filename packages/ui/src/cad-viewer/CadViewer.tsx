import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { ExportControls } from '../export/ExportControls.js';
import type { CadProject, CadProjectRef, CadWorkspaceService } from '@cad/core/client';
import { FileViewer } from '../file-viewer/FileViewer.js';
import { ViewerLoadingOverlay } from '../file-viewer/presentation.js';
import { EmptyState, StatusAction } from '../file-viewer/navigation/index.js';
import type { AppSetting, ColorSchemeSetting, FileProject, LanguageSetting, ViewerHistory } from '../file-viewer/types.js';
import { I18nProvider, translator } from '../i18n/index.js';
import type { HomeLocation, ViewerHost } from '../host/types.js';
import type { LiveRegistry } from '../host/liveRegistry.js';
import { ModelLibrary, RECENTS, type LibraryModel, type LibraryOrigin, type ModelLibrarySource } from '../library/ModelLibrary.js';
import { useModelThumbnail } from '../library/thumbnails.js';
import { OffscreenPicture, cadRenderers, type ModelPictureSource } from './OffscreenPicture.js';
import type { LibraryLayout, LibrarySort } from '../tab-store/tabRecord.js';
import type { TabStore } from '../tab-store/tabStore.js';
import { useTabViewerState } from '../tab-store/useTabViewerState.js';
import { normalizePath } from './catalog.js';
import { isDocumentId } from '@cad/core/lib/cadRefs.js';
import { MissingCadFile } from './MissingCadFile.js';
import { ControlUsageProvider } from '../usage/controls.js';
import { WhatsNewDialog } from '../whats-new/WhatsNewDialog.js';
import { DocumentSearch, useDocumentSearch } from '../search/DocumentSearch.js';

// A STEP: read by the engine, at a length its size decides (the home's pictures ask first, as
// they do for a model's document, by its id).
const STEP_FILE = /\.(?:step|stp)$/i;
// The title of a model's document the engine does not hold, by the state it names (any other: not held).
const NOT_HELD_TITLES: Record<string, string> = { unsaved: "file.notSaved", detached: "file.detached" };
// How often the project of the document on screen is read again while it is shown: a model built or a file written in
// it meanwhile joins its list.
const PROJECT_MS = 3_000;

/**
 * The project `ref` names (the document on screen's: its catalog row's `project`) with its documents, read through the
 * client, again every `PROJECT_MS` while the page is shown and as it is shown again; the same answer twice is not news.
 * null while there is none, and until the first read of it answers.
 */
function useProject(client: CadWorkspaceService, ref: CadProjectRef | null | undefined) {
  const id = ref?.id ?? null;
  const [read, setRead] = useState<{ id: string; project: CadProject | null; error: string | null } | null>(null);
  useEffect(() => {
    const reader = client.project?.bind(client);
    if (!id || !reader) return undefined;
    const controller = new AbortController();
    const load = () => reader(id, { signal: controller.signal }).then(project => {
      if (controller.signal.aborted) return;
      setRead(previous => previous?.id === id && JSON.stringify(previous.project) === JSON.stringify(project) && !previous.error
        ? previous : { id, project, error: null });
    }, error => {
      if (controller.signal.aborted) return;
      setRead(previous => ({ id, project: previous?.id === id ? previous.project : null, error: error instanceof Error ? error.message : String(error) }));
    });
    void load();
    const again = () => { if (document.visibilityState !== 'hidden') void load(); };
    const timer = setInterval(again, PROJECT_MS);
    document.addEventListener('visibilitychange', again);
    return () => { controller.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', again); };
  }, [client, id]);
  return read?.id === id ? read : null;
}

/** The folder a path is in, `/`-separated. */
const folderOf = (path: string) => path.slice(0, Math.max(path.lastIndexOf('/'), 0)) || '/';

export interface CadViewerProps<Model extends LibraryModel = LibraryModel> {
  /** The CAD client: the catalog of the files on screen, and every document's resources. */
  client: CadWorkspaceService;
  /**
   * The host's ports: its files (`createCadFileSource`), clipboard, prompt destination, file
   * actions, links and environment. Navigation is this component's: it shows a file through `onShow`. Of a host's
   * navigation it takes only what it cannot know: a target's own address (`hrefOf`) and how to open one beside this
   * view (`openBeside`), where the host has them, for the home's links and its menus' Open in new tab.
   */
  host: Omit<ViewerHost, 'navigation'> & { navigation?: Pick<ViewerHost['navigation'], 'hrefOf' | 'openBeside'> };
  /**
   * The tab's one store: the renderers' preferences, the viewer's state, the home's layout, and the
   * view of the file on screen, the only file view the tab keeps: leaving a file sets its view aside
   * for the page, which gives it back as the file is shown again.
   */
  tabStore: TabStore;
  /** The host's handle on the mounted view: its agent reads it, and the library's pictures come through it. */
  live: LiveRegistry;
  /** The file on screen, by its absolute path, or a document the engine holds by its id alone (a model's); `''` is none: the home. */
  file: string;
  /**
   * The name of the document `file` names, where the host knows it before the catalog has it (the
   * library's card it was opened from, a document shown before): the navbar's name until the
   * catalog's row names it. Without either, a document named by its id has its name's place empty.
   */
  name?: string;
  /** Show another file (absolute), or the home (`''`) at a place on it (`place`; Recents with none). */
  onShow(file: string, place?: HomeLocation): void;
  /**
   * The place of the home on screen, where the host keeps it (the web's address, the CAD app's history): Recents,
   * Pinned, Standalone or a project's page. Without it this component keeps its own, from Recents.
   */
  place?: HomeLocation;
  /** The home is on screen at `place`, named as the person reads it ("Recents", a project's name): a host titles its page with it. */
  onHomeShown?(place: HomeLocation, name: string): void;
  /**
   * The file on screen once the catalog has it, or null (the home, or a file still resolving or
   * missing), and its document's id: what the host names it by (`/<id>`).
   */
  onShown?(file: string | null, id: string | null): void;
  /**
   * The home's library: the projects and the documents opened before, to open again. A host with one shows it
   * wherever no file is open, and the navbar's logo leads to it from a file; a document in a project has its project's
   * name before its own, which leads to the home at that project, and [ and ] move through its project; ⌘K searches
   * every document in it. Without one (a host whose own navigation shows one file, as a file handler does) a view has a
   * file and nothing else: no home, no project, no search, and no link to another file.
   */
  library?: ModelLibrarySource<Model>;
  /**
   * Keep the library's picture of a model: the file on screen once it has settled, and on the home a
   * card's.
   */
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
   * The view's own history, where the host keeps one rather than a browser (the CAD app's views):
   * Back and Forward in the navbar after its logo, over every file and on the home.
   */
  history?: ViewerHistory;
  /**
   * The host's Full size button, where it shows the view small (inline in a conversation) and can
   * show it full size: the navbar's host action, at its right end, over every file
   * and on the home. Nothing where there is no navbar (`chrome: "bare"`). (A host's way to open what
   * is shown in a page of its own, the CAD app's browser page, is a file action, `fileActions.perform.browser`:
   * the file menu's Open in › Browser.)
   */
  fullSize?: ReactNode;
  /** The chrome around the view (`FileViewerProps.chrome`): the navbar (`"page"`, the default), or the view alone (`"bare"`). */
  chrome?: "page" | "bare";
  /**
   * What's new (`@cad/ui/whats-new`'s `useWhatsNew`): the release whose notes to show, once something
   * is on screen -- the home, or a file's view, never its loading page -- and how they are dismissed.
   * A host leaves it out where a dialog has no room, or while a notice of its own covers the view.
   */
  whatsNew?: { entry: string | null; onDismiss(): void };
  onError?(error: Error): void;
}

const reportError = (error: Error) => console.error(error);
const isPlace = (value: unknown): value is HomeLocation => {
  const view = (value as { view?: unknown } | null | undefined)?.view;
  return view === 'recents' || view === 'pinned' || view === 'standalone'
    || (view === 'project' && typeof (value as { project?: unknown }).project === 'string');
};

/**
 * The viewer every app shows: the shared FileViewer over one file at a time, by absolute path,
 * with its seven renderers (an engine document, which a STEP opens as; DXF; a KiCad board; a KiCad schematic; GLB; STL/3MF;
 * URDF/SRDF), the host's home (the model
 * library) wherever no file is open, and the standard loading and "File does not exist" pages. It
 * follows the catalog of the file on screen and refreshes it when the page is focused or shown
 * again. It keeps a picture of each model it shows for the library (`onThumbnail`), and on the home
 * draws one for a card that has none or an old one: out of sight, with its own client, one model at a
 * time, and only a model whose display is already built — the home never starts a build. It never
 * navigates: showing a file, or the home, is the host's `onShow`.
 */
export function CadViewer<Model extends LibraryModel = LibraryModel>({ client, host, tabStore, live, file, name, onShow, onShown,
  place: placed, onHomeShown, library, onThumbnail, colorScheme, language, appSettings, notice, fullSize, history, chrome, whatsNew, onError = reportError }: CadViewerProps<Model>) {
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
  const latest = useRef({ onShow, onShown, onHomeShown, onThumbnail, path, shown: null as string | null });
  latest.current = { onShow, onShown, onHomeShown, onThumbnail, path, shown: latest.current.shown };

  // The file on screen once the catalog has it: its row joined by the document's id, so a symlink and
  // its target, or two spellings of one path, are one row (`client.entryOf`).
  const entry = path ? (client.entryOf ? client.entryOf(path) : catalog.entries.find(item => normalizePath(item.file) === path) ?? null) : null;
  // What is on screen by its own name: the file's path, or the id of a document with no file of its
  // own (a model's). `file` may name it either way: a host addresses documents by id.
  const shown = entry ? (entry.sourcePath === null ? path : normalizePath(entry.file)) : null;
  const shownId = entry ? String(entry.id || '') || null : null;
  latest.current.shown = shown;
  useEffect(() => { latest.current.onShown?.(shown, shownId); }, [shown, shownId]);

  // Only the file on screen keeps its view in the tab (`tab-store`): leaving a file — for another
  // file, or for the home — sets its camera, Display settings, pose and the rest aside for the page,
  // and showing it again in the same page gives them back, as a reload of the tab (which shows the
  // same file) brings back the file on screen's; an update of the model keeps them. The departing
  // renderer writes its view once more as it unmounts; that write is a cleanup of the commit that
  // changed `file`, and every cleanup of a commit runs before its effects, this one included, so the
  // view set aside is its last. The file shown has its view back in the record before its renderer
  // reads it: a file opens only once its document has loaded, after this effect. The tab's settings
  // are not a file's, and stay. A view is kept under the file's own name (`shown`), and a host may
  // address the file by its document's id: until the catalog says which file that is (a reload, as
  // the page starts), nothing is set aside, or the reload would lose the very view it is meant to
  // bring back.
  useEffect(() => { if (!path || shown) tabStore.files.retain(shown); }, [tabStore, path, shown]);

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

  // What is on screen joins the library with a picture, once it has settled: a file by its path, a
  // model's document by its id, each at its revision (a model's row's is the build the engine holds),
  // so a model rebuilt while it is open is pictured again as a file written again is.
  useModelThumbnail(live, shown, String(entry?.documentHash || entry?.hash || ''),
    (png, pictured) => latest.current.onThumbnail?.(png, pictured) ?? Promise.resolve());
  // Something on screen to say What's new over: the home, or a file's view once its renderer is up
  // (past the loading page), never a file that would not open.
  const viewing = useSyncExternalStore(live.subscribe, live.current, live.current);
  const onScreen = !path || Boolean(viewing);

  // A file the viewer asks for — the project's next with ], a renderer's link — is shown by the host.
  // A view with no library shows its file and nothing else: it opens no other, and has no home.
  const openFile = useCallback((next: string) => {
    const wanted = normalizePath(next);
    if (wanted && wanted !== latest.current.path && wanted !== latest.current.shown) latest.current.onShow(wanted);
  }, []);
  const homed = Boolean(library);
  // The home, at a place on it: the host's where it keeps the place (`place`), else this view's own.
  const [ownPlace, setOwnPlace] = useState<HomeLocation>(RECENTS);
  const place = placed ?? ownPlace;
  const home = useCallback((location?: HomeLocation) => {
    // Anything but a place (a press's event, handed on by a button) is the home's first place.
    const next = isPlace(location) ? location : RECENTS;
    setOwnPlace(next);
    latest.current.onShow('', next);
  }, []);
  // The person's home folder (the server's): the home says a project's folder from `~` in it.
  const [homeFolder, setHomeFolder] = useState<string | null>(null);
  useEffect(() => {
    if (!homed) return undefined;
    const controller = new AbortController();
    void Promise.resolve().then(() => client.serverInfo({ signal: controller.signal })).then(info => { if (typeof info.home === 'string' && info.home) setHomeFolder(info.home); }, () => {});
    return () => controller.abort();
  }, [client, homed]);
  // What only the host knows of navigation: a target's address and how to open one beside this view. A view with no
  // home has neither.
  const hrefOf = host.navigation?.hrefOf, openBeside = host.navigation?.openBeside;
  const links = useMemo(() => ({ ...(hrefOf ? { hrefOf } : {}), ...(openBeside ? { openBeside } : {}) }), [hrefOf, openBeside]);
  const viewerHost = useMemo<ViewerHost>(() => ({ ...host, navigation: homed ? { openFile, home, ...links } : {} }), [host, openFile, home, homed, links]);

  // The project the document on screen is in (its row's, the nearest project above its file or its script): its name
  // before the document's, which shows that project's page on the home with the document just left remembered (`left`:
  // its card is ringed there, and Back and Escape return to it), and its documents, which [ and ] move through. A host
  // with no home has neither. The document is remembered until another is shown, or the home is at another place.
  const [left, setLeft] = useState<(LibraryOrigin & { file: string; project: string }) | null>(null);
  const origin = left && !path && place.view === 'project' && place.project === left.project ? left : null;
  const forgotten = Boolean(left) && (path ? path !== left?.file : !origin);
  useEffect(() => { if (forgotten) setLeft(null); }, [forgotten]);
  const back = useCallback(() => { if (left) latest.current.onShow(left.file); }, [left]);
  const shownName = String(entry?.name || '') || name || '';
  const projectRef = homed ? (entry?.project as CadProjectRef | null | undefined) ?? null : null;
  const projectRead = useProject(client, projectRef);
  const project = useMemo<FileProject | null>(() => (projectRef ? {
    id: projectRef.id, name: projectRef.name, root: projectRef.root,
    documents: projectRead?.project?.documents ?? null, truncated: Boolean(projectRead?.project?.truncated),
    missing: Boolean(projectRead?.project?.missing), error: projectRead?.project ? null : projectRead?.error ?? null,
    href: hrefOf?.({ home: { view: 'project', project: projectRef.id } }) ?? null,
    onShow: () => {
      const { path: file, shown: own } = latest.current;
      setLeft({ file, path: own ?? file, id: shownId, name: shownName, project: projectRef.id });
      home({ view: 'project', project: projectRef.id });
    },
  } : null), [projectRef?.id, projectRef?.name, projectRef?.root, projectRead, hrefOf, home, shownId, shownName]);
  // A document in no project: its ⋯'s Import its folder as a project, the host's chooser starting at its folder (a
  // model's script's), so the person picks the level. Its row says the project it is in once the catalog is read again.
  const importFolder = library?.importFolder;
  const source = entry ? (entry.sourcePath === null ? (typeof entry.script === 'string' ? entry.script : '') : String(entry.file || '')) : '';
  const onImportFolder = useMemo(() => (homed && importFolder && source ? () => {
    void importFolder(folderOf(normalizePath(source))).then(imported => {
      if (imported) void client.refresh({ markRefreshing: false }).catch(() => {});
    }).catch(error => onError(error instanceof Error ? error : new Error(String(error))));
  } : null), [homed, importFolder, source, client, onError]);

  // The home's pictures for cards without a current one, drawn out of sight one at a time and kept as
  // the file on screen's are. A STEP or a model's document the engine does not hold is left to
  // its placeholder: the home never starts the engine's read of a STEP (a large one's is long) nor a
  // model's build, it only asks; a model that is `unsaved` or `detached` is held by none.
  const [drawing, setDrawing] = useState<{ source: ModelPictureSource; done(kept: boolean): void } | null>(null);
  const drawable = Boolean(library && onThumbnail);
  const picture = useMemo(() => (drawable ? async (model: Model) => {
    const file = normalizePath(model.path);
    if (latest.current.path) return false;
    if ((STEP_FILE.test(file) || isDocumentId(file)) && !(await client.engineHolds?.(file).catch(() => false))) return false;
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

  // The home's layout and its order, the tab's (`tab-store`): kept as the person leaves the home and comes back.
  const { layout, sort } = settings.library;
  const changeLayout = useCallback((next: LibraryLayout) => preferences.update({ library: { ...preferences.getSnapshot().library, layout: next } }), [preferences]);
  const changeSort = useCallback((next: LibrarySort) => preferences.update({ library: { ...preferences.getSnapshot().library, sort: next } }), [preferences]);
  const placeShown = useCallback((shownAs: string) => { if (!latest.current.path) latest.current.onHomeShown?.(place, shownAs); }, [place]);
  // A file that will not open says why, with the way home where the host has one.
  const goHome = useMemo(() => homed ? <StatusAction onClick={() => home()}>{t("file.goHome")}</StatusAction> : null, [homed, home, t]);
  const presentation = useMemo(() => ({
    home: library ? <ModelLibrary library={library} layout={layout} onLayoutChange={changeLayout} sort={sort} onSortChange={changeSort} picture={picture}
      fileActions={host.fileActions} place={place} onPlaceChange={home} onPlaceShown={placeShown} from={origin} onBack={back} navigation={links}
      home={homeFolder} /> : undefined,
    // On the viewport's Background as the tab has it, as the view's own cover and its picture are: no flash between them.
    loading: <div className="relative h-full"><ViewerLoadingOverlay viewerLoading background={settings.viewportBackground} /></div>,
    // A document named by its id that the engine does not hold says why, and the command that
    // builds it again (the engine's words), under a title of the state the engine names; a file
    // that is not there, its path.
    error: ({ message, missing, error, reload }: { message: string; missing: boolean; error?: unknown; reload?: () => void }) => missing
      ? <MissingCadFile file={path} entry={entry} reload={reload} action={goHome}
        title={isDocumentId(path) ? t(NOT_HELD_TITLES[String((error as { state?: unknown } | null)?.state)] ?? "file.notHeld") : t("file.missing")}
        description={isDocumentId(path) ? message : undefined} />
      : <EmptyState title={t("file.openFailed")} description={message} action={goHome} />,
  }), [library, layout, changeLayout, sort, changeSort, path, picture, host.fileActions, place, home, placeShown, origin, back, links, homeFolder, entry, goHome, t, settings.viewportBackground]);
  // The search of every document (⌘K, the app menu's Search documents), over a document and the home alike, where
  // the host has a library (`search/`).
  const search = useDocumentSearch();
  const searchCurrent = useMemo(() => ({ id: shownId, path: shown, project: projectRef ? { id: projectRef.id, name: projectRef.name } : null }),
    [shownId, shown, projectRef?.id, projectRef?.name]);
  // What a person does on the screen is counted for the host (`usage/controls.js`); never what a picture drawn
  // out of sight does, which is outside it.
  return <I18nProvider locale={locale}>
    <ControlUsageProvider report={host.usage?.controls}>
    <ExportControls service={client.exports} downloads={host.downloads} file={shown ?? path}>{({ menu, overlay }) => <FileViewer navbarActions={fullSize} fileMenuItems={menu}
      overlay={<>{overlay}{library ? <DocumentSearch search={search} library={library} navigation={viewerHost.navigation} current={searchCurrent} onError={onError} /> : null}</>}
      onSearch={library ? search.show : null} file={path || null} name={String(entry?.name || '') || name} filePath={shown} host={viewerHost} renderers={renderers} state={state} onStateChange={onStateChange}
      colorScheme={colorScheme} language={language} appSettings={appSettings} history={history} project={project} onImportFolder={onImportFolder} notice={notice} chrome={chrome} onError={onError} presentation={presentation} />}</ExportControls>
    </ControlUsageProvider>
    {whatsNew && onScreen ? <WhatsNewDialog entry={whatsNew.entry} onDismiss={whatsNew.onDismiss} /> : null}
    {drawing && !path ? <OffscreenPicture key={drawing.source.file} source={drawing.source} host={host} preferences={preferences} onDone={drawn} /> : null}
  </I18nProvider>;
}
