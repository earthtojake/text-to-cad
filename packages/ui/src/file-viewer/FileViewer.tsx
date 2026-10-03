import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { FileText, RotateCw } from "lucide-react";
import { Component, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Button } from "../primitives/button.jsx";
import { Spinner } from "../primitives/spinner.js";
import { clampPanelWidth, EmptyState, FILE_PANEL_TREE, FileExplorer, FilePanelColumn, FileTree, nextOpenPanel, PanelToggle, PANEL_DEFAULT_WIDTH, resolveOpenPanel, treePanel, ViewerNavbar } from "./navigation/index.js";
import { useFileDocument } from "./hooks/useFileDocument.js";
import { useFileNavigation } from "./hooks/useFileNavigation.js";
import type { FileNavigationAction, FileViewerProps, JsonValue, FileViewerState } from "./types.js";
import { ViewerMobileContext, useViewerMobileMeasure } from "./responsive.js";
import { ViewerElementContext, ViewerHostContext } from '../host/context.js';
import { useLiveDocument } from '../host/useLiveDocument.js';

class RenderBoundary extends Component<{ children: ReactNode; onError?: (error: Error) => void }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, _info: ErrorInfo) { this.props.onError?.(error); }
  render() { return this.state.error ? <EmptyState icon={FileText} title="Could not display that file" description={this.state.error.message} tone="warn" /> : this.props.children; }
}

/** The complete file tab. Its only knowledge of formats comes from registrations. */
export function FileViewer({ file, host, renderers, state, onStateChange, displayActions, settings, notice, navigationPath, reveal, onError, presentation }: FileViewerProps) {
  const source = host.files;
  const onOpenFile = host.navigation.openFile;
  // A renderer opens files in a new view unless it says otherwise.
  const openFromRenderer = useCallback((next: string, options?: { target: "current" | "new" }) => onOpenFile(next, options ?? { target: "new" }), [onOpenFile]);
  const appearance = host.environment;
  const session = useFileDocument(file, source, renderers, host.documents?.drafts);
  const { loaded, document, key, path, reload } = session;
  useLiveDocument(host, path, document);
  const selectedPath = navigationPath === undefined ? path : navigationPath;
  const currentKey = useRef(key);
  currentKey.current = key;
  const latest = useRef({ state, onStateChange, sourceId: source.id });
  latest.current = { state, onStateChange, sourceId: source.id };
  const changeState = useCallback((update: (previous: FileViewerState) => FileViewerState) => {
    const current = latest.current;
    const next = update(current.state);
    latest.current = { ...current, state: next };
    current.onStateChange(next);
  }, []);

  const navigation = useFileNavigation({ source, actions: host.fileActions, state, onStateChange, onOpenFile, path: selectedPath, onError });
  // Width matters only as the breakpoint: this state changes when it is crossed, never per pixel.
  const [rootRef, mobile] = useViewerMobileMeasure();
  // Mobile sheets are deliberate, temporary openings. Keep the wide layout's panel preference intact.
  const [mobilePanel, setMobilePanel] = useState("");
  useEffect(() => { setMobilePanel(""); }, [key, mobile]);
  const setPanel = useCallback((panel: string) => {
    if (currentKey.current !== key) return;
    if (mobile) setMobilePanel(panel);
    else changeState(previous => ({ ...previous, panel }));
  }, [changeState, key, mobile]);
  const [bodyElement, setBodyElement] = useState<HTMLDivElement | null>(null);
  const viewerElement = useRef<HTMLDivElement | null>(null);
  const bindElement = useCallback((element: HTMLDivElement | null) => { viewerElement.current = element; rootRef(element); }, [rootRef]);
  const [panelSlot, setPanelSlot] = useState<HTMLDivElement | null>(null);
  const [navbarSlot, setNavbarSlot] = useState<HTMLDivElement | null>(null);
  // A renderer showing its file fullscreen has the page to itself, until it says otherwise or goes.
  const [fullscreen, setFullscreen] = useState(false);
  useEffect(() => { setFullscreen(false); }, [key]);
  const onFullscreenChange = useCallback((full: boolean) => { if (currentKey.current === key) setFullscreen(full); }, [key]);
  const [readiness, setReadiness] = useState<{ key: string; ready: boolean } | null>(null);
  const [navActions, setNavActions] = useState<{ key: string; actions: readonly FileNavigationAction[] } | null>(null);
  const onNavigationActionsChange = useCallback((actions: readonly FileNavigationAction[]) => { if (currentKey.current === key) setNavActions({ key, actions }); }, [key]);
  const onReady = useCallback((ready: boolean) => { if (currentKey.current === key) setReadiness((previous) => previous?.key === key && previous.ready === ready ? previous : { key, ready }); }, [key]);
  const ready = loaded.status === "ready" && (readiness?.key === key ? readiness.ready : true);
  const declared = (open: string) => loaded.status === "ready" ? loaded.prepared.panels?.({ open, ready, file: loaded.file }) ?? [] : [];
  const panelsAt = (open: string) => [...declared(open), ...(source.list ? [treePanel(open)] : [])];
  const requestedPanel = mobile ? mobilePanel : state.panel;
  const openId = resolveOpenPanel(panelsAt(requestedPanel ?? ""), requestedPanel)?.id ?? "";
  const panels = panelsAt(openId);
  const openPanel = panels.find((panel) => panel.id === openId);
  const collapsePanel = useCallback(() => changeState(previous => ({ ...previous, panel: "", panelWidth: PANEL_DEFAULT_WIDTH })), [changeState]);
  // A desktop viewer is at least the breakpoint wide, so the panel's own range is the only bound.
  const panelWidth = clampPanelWidth(state.panelWidth);
  const changeWidth = useCallback((nextWidth: number) => changeState((previous) => ({ ...previous, panelWidth: clampPanelWidth(nextWidth) })), [changeState]);
  const rendererStateKey = loaded.status === "ready" ? JSON.stringify([loaded.file.path, loaded.renderer.id]) : "";
  // A departing renderer flushes its last per-file state during unmount. That
  // write belongs to its own key even after another file in this root opens;
  // whether it is kept is the host's (`CadViewer` keeps the file on screen's alone,
  // and drops this one once it has landed).
  const setRendererState = useCallback((value: JsonValue) => { if (latest.current.sourceId === source.id && rendererStateKey) changeState((previous) => ({ ...previous, renderers: { ...previous.renderers, [rendererStateKey]: value } })); }, [changeState, rendererStateKey, source.id]);

  // The renderer is re-rendered only when what it is handed changes: not by a panel drag, a
  // navbar action it published, or anything else this frame redraws for itself. Its `state` is the
  // record as it stood when this renderer opened the file: what it saves after that is its own and
  // does not come back to it, so a save never re-renders the view that made it.
  const openedState = useRef<{ key: unknown; value: JsonValue | undefined }>({ key: undefined, value: undefined });
  const openedKey = `${String(key)}\u0000${rendererStateKey}`;
  if (openedState.current.key !== openedKey) openedState.current = { key: openedKey, value: state.renderers?.[rendererStateKey] };
  const rendererState = openedState.current.value;
  const shown = loaded.status === "ready" ? loaded : null;
  const rendererBody = useMemo(() => {
    if (!shown) return null;
    const Renderer = shown.prepared.Component;
    return <RenderBoundary key={key} onError={onError}><Renderer displayActions={displayActions} notice={notice} key={key} file={shown.file} source={source} document={document}
      openPanel={openId} panelSlot={panelSlot} navbarSlot={navbarSlot} onFullscreenChange={onFullscreenChange} onPanelOpen={setPanel} onReady={onReady}
      onNavigationActionsChange={onNavigationActionsChange}
      onOpenFile={openFromRenderer} appearance={appearance}
      state={rendererState} onStateChange={setRendererState} reload={reload} /></RenderBoundary>;
  }, [shown, key, onError, displayActions, notice, source, document, openId, panelSlot, navbarSlot, onFullscreenChange, setPanel, onReady,
    onNavigationActionsChange, openFromRenderer, appearance, rendererState, setRendererState, reload]);

  // A host's home stands where no file is open, as a page of its own.
  const home = loaded.status === "empty" ? presentation?.home : undefined;
  let body: ReactNode;
  if (loaded.status === "empty") body = home ?? presentation?.empty ?? <EmptyState icon={FileText} title="No file open" />;
  else if (loaded.status === "loading") body = presentation?.loading ?? <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground" role="status"><Spinner className="size-3.5" />Opening…</div>;
  else if (loaded.status === "error") body = presentation?.error?.(loaded.message) ?? <EmptyState icon={FileText} title="Could not open that file" description={loaded.message} tone="warn" />;
  else body = rendererBody;
  const shownActions = navActions?.key === key && ready ? navActions.actions : [];
  const treeOpen = openPanel?.content === "tree" && !fullscreen;
  const columnPanel = openPanel && openPanel.content === "slot" && !fullscreen ? openPanel : null;
  const explorer = panels.some(panel => panel.id === FILE_PANEL_TREE) ? { open: treeOpen, onToggle: () => setPanel(nextOpenPanel(openId, FILE_PANEL_TREE)) } : null;
  // With a file asked for, the navbar leads back to the host's home.
  const onBack = file ? host.navigation.home : undefined;
  const dirty = document?.dirty ? <TooltipHint content="Unsaved changes"><span aria-label="Unsaved changes" className="ml-1 size-1.5 shrink-0 rounded-full bg-foreground/60" /></TooltipHint> : null;
  const trailing = shownActions.length || panels.some(panel => panel.id !== FILE_PANEL_TREE) ? <>
    {shownActions.map(({ id, label, hint, icon: Icon, disabled, active, onInvoke }) => <TooltipHint key={id} content={hint ?? label}><Button type="button" variant="ghost" size="icon-xs" className="size-6 text-muted-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground" aria-label={label} disabled={disabled} aria-pressed={active} onClick={() => { try { void Promise.resolve(onInvoke()).catch(error => onError?.(error)); } catch (error) { onError?.(error instanceof Error ? error : new Error(String(error))); } }}><Icon className="size-3.5" aria-hidden="true" /></Button></TooltipHint>)}
    {panels.filter(panel => panel.id !== FILE_PANEL_TREE).map((panel) => <PanelToggle key={panel.id} id={panel.id} active={panel.id === openId} icon={panel.icon} label={panel.label} onClick={() => setPanel(nextOpenPanel(openId, panel.id))} />)}
  </> : null;
  // The navbar is drawn only to hold something — the way back home, the explorer, the file's name,
  // its actions, the host's links — and never over the host's home, which holds its links itself,
  // or for a view shown small in a conversation (`compact`), whose frame already says what it
  // shows. A host that shows one file without browsing it or naming it, with nothing at either
  // end, gets the file with no row above it.
  const navbar = !appearance.compact && !home && !fullscreen && (Boolean(host.links) || Boolean(settings) || Boolean(onBack) || Boolean(explorer) || navigation.file !== null || Boolean(trailing) || Boolean(dirty));
  return <ViewerMobileContext.Provider value={mobile}><ViewerHostContext.Provider value={host}><ViewerElementContext.Provider value={viewerElement}><div className="text-to-cad-file-viewer text-ui font-normal flex h-full min-h-0 min-w-0 flex-col overflow-hidden" ref={bindElement} data-viewer-layout={mobile ? "mobile" : "desktop"} tabIndex={-1}>
    {navbar ? <ViewerNavbar onBack={onBack} explorer={explorer} file={navigation.file} selecting={loaded.status === "empty"} status={dirty} trailing={trailing} settings={settings} controlsRef={setNavbarSlot}
      links={host.links} platform={appearance.platform} clipboard={host.clipboard} onError={onError} /> : null}
    {document?.stale ? <div className="flex shrink-0 items-center gap-2 border-b bg-amber-500/10 px-3 py-1.5 text-xs text-amber-700 dark:text-amber-400" role="status">
      <RotateCw className="size-3.5 shrink-0" /><span className="flex-1">This file changed on disk since you opened it.</span>
      <Button className="h-6 px-2 text-xs font-normal" onClick={document.reload} size="sm" variant="secondary">Reload</Button>
      <Button className="h-6 px-2 text-xs font-normal" onClick={document.keepMine} size="sm" variant="ghost">Keep mine</Button>
    </div> : null}
    {document?.error ? <div className="flex shrink-0 items-center gap-2 border-b bg-destructive/10 px-3 py-1.5 text-xs text-destructive" role="alert">
      <span className="flex-1">Could not save: {document.error}</span><Button className="h-6 px-2 text-xs font-normal" size="sm" variant="secondary" onClick={() => void document.save()}>Try again</Button>
    </div> : null}
    <div ref={setBodyElement} className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden">
      <div className="min-w-0 flex-1 overflow-hidden">{body}</div>
      {columnPanel ? <FilePanelColumn mobile={mobile} portalContainer={bodyElement} onDismiss={() => setPanel("")} id={columnPanel.id} label={columnPanel.label} width={panelWidth} onWidthChange={changeWidth} onCollapse={collapsePanel}>
        <div className="h-full min-h-0" ref={setPanelSlot} />
      </FilePanelColumn> : null}
      {/* The explorer floats over the body's left, never beside it: opening it resizes nothing. */}
      {treeOpen ? <FileExplorer label="Files" mobile={mobile} portalContainer={bodyElement} onDismiss={() => setPanel("")} width={panelWidth} onWidthChange={changeWidth} onCollapse={collapsePanel}>
        <FileTree key={source.id} source={navigation.tree} activePath={selectedPath} edit={navigation.edit} reveal={reveal} onOpen={(next) => { if (mobile) setMobilePanel(""); onOpenFile(next, { target: "new", panel: FILE_PANEL_TREE }); }} />
      </FileExplorer> : null}
    </div>
  </div></ViewerElementContext.Provider></ViewerHostContext.Provider></ViewerMobileContext.Provider>;
}
