import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { isDocumentId } from "@cad/core/lib/cadRefs.js";
import { Component, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ErrorInfo, ReactNode, RefObject } from "react";
import { Button } from "../primitives/button.jsx";
import LoadingStep from "../loading/LoadingStep.jsx";
import { EmptyState, ViewerNavbar } from "./navigation/index.js";
import type { EntryAction } from "./navigation/index.js";
import { useFileDocument } from "./hooks/useFileDocument.js";
import type { FileNavigationAction, FileViewerProps, JsonValue, FileViewerState } from "./types.js";
import { ViewerMobileContext, useViewerMobileMeasure } from "./responsive.js";
import { ViewerElementContext, ViewerHostContext } from '../host/context.js';
import { I18nProvider, translator } from "../i18n/index.js";
import { mayTakeKeyboard } from "./takeKeyboard.js";
import { FilePanelContext, filePanelOf, withFilePanel } from "./filePanel.js";
import { PANEL_HEAD_ROW, PANEL_ROW_VARIABLES, PANEL_SURFACE_PX, PanelFrameContext, PanelTogglesContext, clampPanelWidth, sidebarLayout } from "./panelToggles.js";
import { TreeRowsLoading } from "../primitives/tree-row.jsx";
import { NavbarSlotsContext, NavbarViewSlotContext } from "./navbarSlots.js";
import type { PanelToggles } from "./panelToggles.js";
import { PANEL_PEEK_ASIDE_CLASS, PANEL_PEEK_CARD_CLASS, PANEL_PEEK_CARD_STYLE, PANEL_PEEK_CONTENT_STYLE, PanelPeekContext, panelPeekMotionClass, usePanelPeek } from "./panelPeek.js";

class RenderBoundary extends Component<{ children: ReactNode; title: string; onError?: (error: Error) => void }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, _info: ErrorInfo) { this.props.onError?.(error); }
  render() { return this.state.error ? <EmptyState title={this.props.title} description={this.state.error.message} /> : this.props.children; }
}

/**
 * The complete file view: one file, by its absolute path, under the one navbar. Its only knowledge
 * of formats comes from registrations. With no file it shows the host's home.
 */
export function FileViewer({ file, name, filePath = null, host, renderers, state, onStateChange, colorScheme, language, appSettings, history, recent, explorerFolder = null, onExplorerFolderChange, notice, navbarActions, fileMenuItems, overlay, onError, presentation, chrome = "page", layout }: FileViewerProps) {
  // The language the host names (`environment.locale`): this frame's own strings, and everything
  // drawn under it (`I18nProvider`), the nodes the host hands it included.
  const locale = host.environment.locale;
  const t = translator(locale);
  const source = host.files;
  const onOpenFile = host.navigation.openFile;
  const appearance = host.environment;
  const { loaded, key, path, reload } = useFileDocument(file, source, renderers);
  const currentKey = useRef(key);
  currentKey.current = key;
  const reloadCurrent = useCallback(() => { if (currentKey.current === key) reload(); }, [key, reload]);
  const latest = useRef({ state, onStateChange, sourceId: source.id });
  latest.current = { state, onStateChange, sourceId: source.id };
  const changeState = useCallback((update: (previous: FileViewerState) => FileViewerState) => {
    const current = latest.current;
    const next = update(current.state);
    latest.current = { ...current, state: next };
    current.onStateChange(next);
  }, []);

  // Width matters only as the breakpoint: this state changes when it is crossed, never per pixel. A pinned layout
  // (`layout`: a viewer that is not the page's own) is neither measured nor said to the page.
  const [rootRef, measuredMobile] = useViewerMobileMeasure(layout === undefined);
  const mobile = layout ? layout === "mobile" : measuredMobile;
  const viewerElement = useRef<HTMLDivElement | null>(null);
  const bindElement = useCallback((element: HTMLDivElement | null) => { viewerElement.current = element; rootRef(element); }, [rootRef]);
  // The file whose renderer says its Preview is up, while it is: the navbar steps aside for Preview's own bar.
  const [previewing, setPreviewing] = useState<typeof key | null>(null);
  const onPreviewChange = useCallback((on: boolean) => { if (currentKey.current === key) setPreviewing(on ? key : null); }, [key]);
  const [readiness, setReadiness] = useState<{ key: string; ready: boolean } | null>(null);
  // The view's two panel toggles, which its frame says (`panelToggles.js`) and the navbar draws.
  // Keyed by the file it is said for: until this file's view says its own (or none), the navbar draws the one it
  // will have (`pendingToggles`, below).
  const [saidToggles, setSaidToggles] = useState<{ key: string; toggles: PanelToggles | null } | null>(null);
  const setPanelToggles = useCallback((toggles: PanelToggles | null) => setSaidToggles({ key, toggles }), [key]);
  const framed = useRef<string | null>(null);
  const frameSaid = useCallback(() => { framed.current = key; }, [key]);
  // Home's controls' places in the navbar (`navbarSlots.js`), once the navbar has drawn them.
  const [homeLeft, setHomeLeft] = useState<HTMLElement | null>(null);
  const [homeRight, setHomeRight] = useState<HTMLElement | null>(null);
  // The navbar's view slot, where the view on screen puts its view settings (`navbarSlots.js`).
  const [viewSlot, setViewSlot] = useState<HTMLElement | null>(null);
  const [navActions, setNavActions] = useState<{ key: string; actions: readonly FileNavigationAction[] } | null>(null);
  const onNavigationActionsChange = useCallback((actions: readonly FileNavigationAction[]) => { if (currentKey.current === key) setNavActions({ key, actions }); }, [key]);
  const onReady = useCallback((ready: boolean) => { if (currentKey.current === key) setReadiness((previous) => previous?.key === key && previous.ready === ready ? previous : { key, ready }); }, [key]);
  const ready = loaded.status === "ready" && (readiness?.key === key ? readiness.ready : true);
  // A file shown takes the keyboard, so its tool keys (V, M, P …) work with no press in it first:
  // where nothing has it, in a page of its own (never a card in a chat's frame) and never in a compact
  // view drawn out of sight (`takeKeyboard.js`).
  useEffect(() => {
    const element = viewerElement.current;
    if (!ready || !element || appearance.compact) return;
    if (mayTakeKeyboard(element.ownerDocument, element.ownerDocument.defaultView as Window)) element.focus({ preventScroll: true });
  }, [ready, key, appearance.compact]);
  const rendererStateKey = loaded.status === "ready" ? JSON.stringify([loaded.file.path, loaded.renderer.id]) : "";

  // The renderer is re-rendered only when what it is handed changes: not by a navbar action it
  // published, a resize within one layout, or anything else this frame redraws for itself. Its
  // `state` is the record as it stood when this renderer opened the file: what it saves after that
  // is its own and does not come back to it, so a save never re-renders the view that made it.
  const openedState = useRef<{ key: unknown; value: JsonValue | undefined }>({ key: undefined, value: undefined });
  const openedKey = `${String(key)}\u0000${rendererStateKey}`;
  if (openedState.current.key !== openedKey) openedState.current = { key: openedKey, value: state.renderers?.[rendererStateKey] };
  const rendererState = openedState.current.value;
  // The view's panel, the file's (`filePanel.js`): held here for the file on screen, from
  // its record as it opened, and merged into every record its renderer writes, so a renderer that
  // writes its view wholesale never drops it. One holder per file opened: a departing renderer's last
  // write carries its own file's panel.
  // A choice the person made on the stand-in toggle while the file loaded (`pageChoice`, below) is the view's from its
  // first frame, and written with its first record.
  const pageChoice = useRef<{ key: unknown; open: boolean } | null>(null);
  const opened = useMemo(() => {
    const panel = filePanelOf(rendererState) as { open?: boolean };
    const choice = pageChoice.current?.key === key ? pageChoice.current : null;
    return { record: rendererState as JsonValue | undefined, panel: choice ? { ...panel, open: choice.open } : panel as object, chosen: Boolean(choice) };
  }, [openedKey]);
  // A departing renderer flushes its last per-file state during unmount. That write belongs to its
  // own key even after another file opens; whether it is kept is the host's (`CadViewer` keeps the
  // file on screen's alone, and drops this one once it has landed).
  const writeView = useCallback(() => {
    if (latest.current.sourceId !== source.id || !rendererStateKey) return;
    const value = withFilePanel(opened.record, opened.panel) as JsonValue;
    changeState((previous) => ({ ...previous, renderers: { ...previous.renderers, [rendererStateKey]: value } }));
  }, [changeState, rendererStateKey, source.id, opened]);
  const setRendererState = useCallback((value: JsonValue) => { opened.record = value; writeView(); }, [opened, writeView]);
  // `panel` is read live: a renderer that mounts again for the same file (a remount, a layout change)
  // starts from the panel as the person last left it, not as the file opened.
  const filePanel = useMemo(() => ({ get panel() { return opened.panel; }, change: (panel: object) => { opened.panel = panel; writeView(); } }), [opened, writeView]);
  const shown = loaded.status === "ready" ? loaded : null;
  const rendererBody = useMemo(() => {
    if (!shown) return null;
    const Renderer = shown.prepared.Component;
    return <RenderBoundary key={key} title={t("file.displayFailed")} onError={onError}><PanelTogglesContext.Provider value={setPanelToggles}><PanelFrameContext.Provider value={frameSaid}><FilePanelContext.Provider value={filePanel}><Renderer notice={notice} key={key} file={shown.file} source={source}
      onPreviewChange={onPreviewChange} onReady={onReady} onNavigationActionsChange={onNavigationActionsChange}
      onOpenFile={onOpenFile} appearance={appearance}
      state={rendererState} onStateChange={setRendererState} reload={reload} /></FilePanelContext.Provider></PanelFrameContext.Provider></PanelTogglesContext.Provider></RenderBoundary>;
  }, [shown, key, onError, notice, source, onPreviewChange, onReady,
    onNavigationActionsChange, onOpenFile, appearance, rendererState, setRendererState, filePanel, reload, t, setPanelToggles, frameSaid]);

  // The panel before the view is up — the file read, or the view's chunk loading, or the view mounted but its toggle not
  // said yet: the navbar has its toggle from the page's first frame, in the state the view will open it in (the one
  // rule, `sidebarLayout`: the person's choice on the file for this session at any width, else open where the model
  // keeps 640px beside the default-width panel), pressable as the view's is: a press pins or unpins it, the person's
  // choice on the file, which the view opens with and writes (`pageToggle`); collapsed, a mouse resting on it peeks the
  // stand-in over the page (`panelPeek.js`, the view's own peek, which the view takes over). Open, the panel's frame stands in its place, at the
  // width the view will draw (the kept one within its bounds, `clampPanelWidth`; `data-panel-loading`), drawn as the
  // view's own panel is while its file loads: the head's one block (a bar where a lone title's name will be: the tabs are
  // not known yet) over its rule, and the placeholder rows (`TreeRowsLoading`) where the first rows will stand, on the
  // same lines (`panelToggles.js`'s metrics), so nothing moves as the view takes over. A file that will not open has neither.
  const bodyBox = useRef<HTMLDivElement | null>(null);
  const [bodyWidth, setBodyWidth] = useState(0);
  const pending = Boolean(path) && (loaded.status === "loading" || (loaded.status === "ready" && saidToggles?.key !== key));
  useLayoutEffect(() => {
    const element = bodyBox.current;
    if (!pending || !element) return undefined;
    const measure = () => setBodyWidth(Math.round(element.getBoundingClientRect().width));
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [pending]);
  // The file's view as the tab keeps it, by its own path (the host's `filePath` while a document named by its id is read).
  const keptPanel = useMemo(() => {
    if (!pending) return {};
    const paths = new Set([path, filePath].filter(Boolean));
    for (const [stateKey, record] of Object.entries(state.renderers ?? {})) {
      let kept: unknown;
      try { kept = JSON.parse(stateKey)?.[0]; } catch { kept = null; }
      if (typeof kept === "string" && paths.has(kept)) return filePanelOf(record) as { open?: boolean; width?: number };
    }
    return {};
  }, [pending, path, filePath, state.renderers]);
  const pendingWidth = clampPanelWidth(keptPanel.width);
  // The person's choice on the stand-in toggle, for this file, until the view takes it (`opened`, above).
  const [pageOpen, setPageOpen] = useState<{ key: unknown; open: boolean } | null>(null);
  const choice = pageOpen?.key === key ? pageOpen.open : keptPanel.open;
  const pendingOpen = pending && !mobile && sidebarLayout({ frameWidth: bodyWidth, choice, has: true }).mode === "push";
  // The page's one peek (`panelPeek.js`), from its first frame: the stand-in's while the file loads, the view's frame's
  // once it says its toggle (`PanelPeekContext`), so a card up as the view arrives stays up. Enabled as the toggle
  // drawn now says: the view's (`peekable`), else the stand-in's, collapsed on a desktop.
  const said = saidToggles?.key === key && loaded.status === "ready";
  // A view's frame says it once it has measured its width; until then the peek stays as the stand-in had it.
  const saidPeekable = said ? (saidToggles?.toggles ? saidToggles.toggles.left?.peekable : false) : undefined;
  const peekEnabled = useRef(false);
  peekEnabled.current = typeof saidPeekable === "boolean" ? saidPeekable : said ? peekEnabled.current : pending && !mobile && !pendingOpen;
  const peek = usePanelPeek({ enabled: peekEnabled.current });
  const closePeek = peek.close;
  // A press on the stand-in does what the view's toggle does: pins or unpins the panel (a peek, if up, becomes the
  // docked panel in place), the person's choice on this file, which the view opens with and writes (`opened`).
  const pageToggle = useCallback(() => {
    closePeek(false, true);
    const open = !pendingOpen;
    pageChoice.current = { key, open };
    setPageOpen({ key, open });
  }, [closePeek, pendingOpen, key]);
  const pendingToggles = useMemo<PanelToggles | null>(() => (pending ? { left: { open: pendingOpen,
    label: t(pendingOpen ? "flatPanel.hide" : "flatPanel.show"), shortcut: appearance.platform === "darwin" ? "⌘\\" : "Ctrl+\\", toggle: pageToggle,
    hover: mobile ? null : peek.toggleHandlers, peeking: peek.peeking, peekable: !mobile && !pendingOpen } } : null),
    [pending, pendingOpen, appearance.platform, t, pageToggle, mobile, peek.toggleHandlers, peek.peeking]);
  const panelToggles = said ? saidToggles.toggles : pendingToggles;
  // The view's first record carries a choice made on the stand-in.
  useEffect(() => {
    if (loaded.status !== "ready" || !opened.chosen) return;
    opened.chosen = false;
    pageChoice.current = null;
    writeView();
  }, [loaded.status, opened, writeView]);
  // A view with no frame (none said it is one as it rendered: `PanelFrameContext`) has no toggle, from its first frame.
  useLayoutEffect(() => {
    if (loaded.status === "ready" && framed.current !== key) setSaidToggles(previous => (previous?.key === key ? previous : { key, toggles: null }));
  }, [loaded.status, key]);

  let body: ReactNode;
  if (loaded.status === "empty") body = presentation?.home ?? null;
  else if (loaded.status === "loading") {
    // The host's own cover where it has one (a CAD host's is on the viewport's Background), else the one indicator, in
    // the app's theme: a host that knows no viewport has none to follow.
    const loading = presentation?.loading ?? <div className="flex h-full items-center justify-center px-4"><LoadingStep label={t("file.opening")} /></div>;
    const standIn = <>
      <div aria-hidden="true" className="box-content flex shrink-0 items-center px-(--panel-inset)"
        style={{ paddingTop: PANEL_SURFACE_PX, paddingBottom: 0, height: PANEL_HEAD_ROW }} data-panel-head="">
        <span className="block h-2 w-12 rounded-full bg-muted-foreground/20 motion-safe:animate-pulse" data-panel-loading-title="" />
      </div>
      <div className="flex flex-col px-(--panel-inset)" style={{ paddingTop: PANEL_SURFACE_PX }}><TreeRowsLoading label={t("spinner.loading")} /></div>
    </>;
    body = pendingOpen ? <div className="flex h-full min-h-0">
      <aside aria-busy="true" className="relative flex h-full shrink-0 flex-col border-r border-border bg-sidebar text-ui" style={{ ...PANEL_ROW_VARIABLES, width: pendingWidth }}
        data-panel-loading="">{standIn}</aside>
      <div className="min-w-0 flex-1">{loading}</div>
    </div> : peek.shown ? <div className="relative h-full min-h-0">
      {loading}
      {/* Collapsed, a rest on the stand-in toggle peeks the stand-in, as the view's panel peeks (`PanelSurface.jsx`): the
          same card, place, width and slide, which the view takes over where it stands. */}
      <aside ref={peek.panelRef as RefObject<HTMLElement>} aria-busy="true" {...peek.panelHandlers}
        className={`flex min-h-0 flex-col text-ui text-foreground ${PANEL_PEEK_ASIDE_CLASS} ${panelPeekMotionClass({ leaving: peek.leaving, entered: peek.entered })}`}
        style={{ ...PANEL_ROW_VARIABLES, width: pendingWidth }} data-panel-loading="" data-panel-peek="" data-panel-peek-leaving={peek.leaving ? "" : undefined}
        onAnimationEnd={peek.leaving ? event => { if (event.target === event.currentTarget) peek.exited(); } : undefined}>
        <div aria-hidden="true" className={PANEL_PEEK_CARD_CLASS} style={PANEL_PEEK_CARD_STYLE} data-panel-peek-card="" />
        <div className="relative flex min-h-0 flex-1 flex-col" style={PANEL_PEEK_CONTENT_STYLE}>{standIn}</div>
      </aside>
    </div> : loading;
  }
  else if (loaded.status === "error") body = presentation?.error?.({ message: loaded.message, missing: loaded.missing, error: loaded.error, reload: reloadCurrent }) ?? <EmptyState title={t("file.openFailed")} description={loaded.message} />;
  else body = rendererBody;
  const shownActions = navActions?.key === key && ready ? navActions.actions : [];
  const trailing = shownActions.length ? <>
    {shownActions.map(({ id, label, hint, icon: Icon, disabled, active, onInvoke }) => <TooltipHint key={id} content={hint ?? label}><Button type="button" variant="ghost" size="icon-xs" className="size-control shrink-0 rounded-md text-muted-foreground hover:text-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground" aria-label={label} disabled={disabled} aria-pressed={active} onClick={() => { try { void Promise.resolve(onInvoke()).catch(error => onError?.(error)); } catch (error) { onError?.(error instanceof Error ? error : new Error(String(error))); } }}><Icon className="size-4" aria-hidden="true" /></Button></TooltipHint>)}
  </> : null;
  // The on-disk file the view browses from and acts on: the file's own path, or none for a document
  // with no file of its own (a model's, by its id): it has no file menu, and its Files tab starts
  // where the explorer was last, else the person's home folder (`explorerFolder`), never the
  // folder of the script it was built from.
  const navigationPath = shown ? (shown.file.navigationPath === undefined ? shown.file.path : shown.file.navigationPath)
    : path && !isDocumentId(path) ? path : null;
  const model = !navigationPath && Boolean(path) && (shown ? shown.file.navigationPath === null : isDocumentId(path));
  const folder = navigationPath ? null : explorerFolder;
  // The ⋯ menu: what the host can do with the document on screen -- Copy path and Reveal its file on
  // disk (a model's: the script that builds it, where its metadata names one), its page in the
  // browser whatever it is -- and the host's own items (`fileMenuItems`: the viewer's Export).
  const perform = host.fileActions?.perform;
  // Open in's apps, where the host has them: asked by the document's own name as the menu opens.
  const appsOf = host.fileActions?.apps;
  const openApp = host.fileActions?.openApp;
  const onDisk = navigationPath ?? shown?.file.sourceFile ?? null;
  // A source moved or deleted keeps Copy path (where it was) and draws what opens it disabled.
  const sourceMissing = Boolean(shown?.file.sourceMissing);
  const fileMenu = useMemo(() => {
    const capabilities = new Set((Object.keys(perform ?? {}) as EntryAction[])
      .filter(action => action === "browser" || action === "copy-link" ? Boolean(path) : Boolean(onDisk)));
    // The page's own actions (Browser, Copy link) name the document; the rest, its file on disk.
    const target = (action: EntryAction) => action === "browser" || action === "copy-link" ? path : onDisk;
    const document = { path: path ?? "", kind: "file" as const };
    const apps = appsOf && openApp && path ? (options: { signal: AbortSignal }) => appsOf(document, options) : undefined;
    return path && (capabilities.size || fileMenuItems) ? {
      platform: host.fileActions?.platform ?? "linux", capabilities, sourceMissing, items: fileMenuItems, apps,
      onAction: (action: EntryAction | "app", app?: { target: string; app: string }) => {
        const done = action === "app" ? (app ? openApp?.(document, app.target, app.app) : undefined)
          : perform?.[action]?.({ path: target(action) ?? "", kind: "file" });
        void Promise.resolve(done).catch(error => onError?.(error));
      },
    } : null;
  }, [path, onDisk, sourceMissing, perform, appsOf, openApp, host.fileActions?.platform, fileMenuItems, onError]);
  // The name opens its menu where this view shows another document: Files -- the explorer, rooted at
  // the file's folder, or for a model where the explorer was last -- where the host's files can be browsed, and
  // Models, the host's library's models, where it has one. A pick shows the document here. A view that shows
  // its file alone opens neither.
  const explorer = useMemo(() => (navigationPath || folder) && source.list && source.search && onOpenFile
    ? { source, folder, onOpen: onOpenFile, onFolderChange: onExplorerFolderChange } : null,
    [navigationPath, folder, source, onOpenFile, onExplorerFolderChange]);
  const recentMenu = useMemo(() => recent && onOpenFile ? { list: () => recent.list(), onOpen: onOpenFile } : null, [recent, onOpenFile]);
  // The logo's app menu: the host's links and the person's settings (Back to home is `onHome`).
  const menu = useMemo(() => host.links || appSettings?.length || colorScheme || language ? { links: host.links, appSettings, colorScheme, language, platform: appearance.platform } : null,
    [host.links, appSettings, colorScheme, language, appearance.platform]);
  // The navbar is drawn over every file and over the host's home — there only the logo's menu (no
  // Back to home), Back and Forward where the host keeps the view's history, and the host's
  // actions, as over a file — never over a view drawn small with no chrome
  // (`compact`: an offscreen picture), never where the host asks for the view alone (`chrome: "bare"`),
  // and not while the renderer's Preview is up, which draws its own bar in its place.
  const home = loaded.status === "empty" && Boolean(presentation?.home);
  const navbar = (Boolean(path) || home) && !appearance.compact && chrome !== "bare" && previewing !== key;
  const homeSlotRefs = useMemo(() => ({ left: setHomeLeft, right: setHomeRight }), []);
  const homeSlots = useMemo(() => (navbar && !path && home ? { left: homeLeft, right: homeRight } : null), [navbar, path, home, homeLeft, homeRight]);
  return <I18nProvider locale={locale}><ViewerMobileContext.Provider value={mobile}><ViewerHostContext.Provider value={host}><ViewerElementContext.Provider value={viewerElement}><NavbarSlotsContext.Provider value={homeSlots}><NavbarViewSlotContext.Provider value={navbar && path ? viewSlot : null}><PanelPeekContext.Provider value={peek}><div className="text-to-cad-file-viewer text-ui font-normal flex h-full min-h-0 min-w-0 flex-col overflow-hidden" ref={bindElement} data-viewer-layout={layout ? undefined : mobile ? "mobile" : "desktop"} data-viewer-pinned-layout={layout} tabIndex={-1}>
    {navbar ? (path
      ? <ViewerNavbar onHome={host.navigation.home} menu={menu} history={history} file={navigationPath ?? path} name={shown?.file.name || name} kind={model ? "model" : "file"} explorer={explorer} recent={recentMenu} fileMenu={fileMenu} trailing={trailing} actions={navbarActions}
        panels={panelToggles} viewSlot={setViewSlot} />
      : <ViewerNavbar menu={menu} history={history} actions={navbarActions} homeSlots={home ? homeSlotRefs : null} />) : null}
    <div className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden">
      <div ref={bodyBox} className="min-w-0 flex-1 overflow-hidden">{body}</div>
      {overlay}
    </div>
  </div></PanelPeekContext.Provider></NavbarViewSlotContext.Provider></NavbarSlotsContext.Provider></ViewerElementContext.Provider></ViewerHostContext.Provider></ViewerMobileContext.Provider></I18nProvider>;
}
