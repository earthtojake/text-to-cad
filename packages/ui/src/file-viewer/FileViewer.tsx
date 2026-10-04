import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { FileText } from "lucide-react";
import { Component, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Button } from "../primitives/button.jsx";
import { Spinner } from "../primitives/spinner.js";
import { clampPanelWidth, EmptyState, FilePanelColumn, nextOpenPanel, PanelToggle, PANEL_DEFAULT_WIDTH, resolveOpenPanel, ViewerNavbar } from "./navigation/index.js";
import type { EntryAction } from "./navigation/index.js";
import { useFileDocument } from "./hooks/useFileDocument.js";
import type { FileNavigationAction, FileViewerProps, JsonValue, FileViewerState } from "./types.js";
import { ViewerMobileContext, useViewerMobileMeasure } from "./responsive.js";
import { ViewerElementContext, ViewerHostContext } from '../host/context.js';

class RenderBoundary extends Component<{ children: ReactNode; onError?: (error: Error) => void }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, _info: ErrorInfo) { this.props.onError?.(error); }
  render() { return this.state.error ? <EmptyState icon={FileText} title="Could not display that file" description={this.state.error.message} tone="warn" /> : this.props.children; }
}

/**
 * The complete file view: one file, by its absolute path, under the one navbar. Its only knowledge
 * of formats comes from registrations. With no file it shows the host's home.
 */
export function FileViewer({ file, host, renderers, state, onStateChange, displayActions, appSettings, update, fullSize, features, notice, onError, presentation }: FileViewerProps) {
  const source = host.files;
  const onOpenFile = host.navigation.openFile;
  const appearance = host.environment;
  const { loaded, key, path, reload } = useFileDocument(file, source, renderers);
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
  // A renderer showing its file fullscreen has the page to itself, until it says otherwise or goes.
  const [fullscreen, setFullscreen] = useState(false);
  useEffect(() => { setFullscreen(false); }, [key]);
  const onFullscreenChange = useCallback((full: boolean) => { if (currentKey.current === key) setFullscreen(full); }, [key]);
  const [readiness, setReadiness] = useState<{ key: string; ready: boolean } | null>(null);
  const [navActions, setNavActions] = useState<{ key: string; actions: readonly FileNavigationAction[] } | null>(null);
  const onNavigationActionsChange = useCallback((actions: readonly FileNavigationAction[]) => { if (currentKey.current === key) setNavActions({ key, actions }); }, [key]);
  const onReady = useCallback((ready: boolean) => { if (currentKey.current === key) setReadiness((previous) => previous?.key === key && previous.ready === ready ? previous : { key, ready }); }, [key]);
  const ready = loaded.status === "ready" && (readiness?.key === key ? readiness.ready : true);
  const panelsAt = (open: string) => loaded.status === "ready" ? loaded.prepared.panels?.({ open, ready, file: loaded.file }) ?? [] : [];
  const requestedPanel = mobile ? mobilePanel : state.panel;
  const openId = resolveOpenPanel(panelsAt(requestedPanel ?? ""), requestedPanel)?.id ?? "";
  const panels = panelsAt(openId);
  const openPanel = panels.find((panel) => panel.id === openId);
  const collapsePanel = useCallback(() => changeState(previous => ({ ...previous, panel: "", panelWidth: PANEL_DEFAULT_WIDTH })), [changeState]);
  // A desktop viewer is at least the breakpoint wide, so the panel's own range is the only bound.
  const panelWidth = clampPanelWidth(state.panelWidth);
  const changeWidth = useCallback((nextWidth: number) => changeState((previous) => ({ ...previous, panelWidth: clampPanelWidth(nextWidth) })), [changeState]);
  const rendererStateKey = loaded.status === "ready" ? JSON.stringify([loaded.file.path, loaded.renderer.id]) : "";
  // A departing renderer flushes its last per-file state during unmount. That write belongs to its
  // own key even after another file opens; whether it is kept is the host's (`CadViewer` keeps the
  // file on screen's alone, and drops this one once it has landed).
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
    return <RenderBoundary key={key} onError={onError}><Renderer displayActions={displayActions} notice={notice} features={features} key={key} file={shown.file} source={source}
      openPanel={openId} panelSlot={panelSlot} onFullscreenChange={onFullscreenChange} onPanelOpen={setPanel} onReady={onReady}
      onNavigationActionsChange={onNavigationActionsChange}
      onOpenFile={onOpenFile} appearance={appearance}
      state={rendererState} onStateChange={setRendererState} reload={reload} /></RenderBoundary>;
  }, [shown, key, onError, displayActions, notice, features, source, openId, panelSlot, onFullscreenChange, setPanel, onReady,
    onNavigationActionsChange, onOpenFile, appearance, rendererState, setRendererState, reload]);

  let body: ReactNode;
  if (loaded.status === "empty") body = presentation?.home ?? null;
  else if (loaded.status === "loading") body = presentation?.loading ?? <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground" role="status"><Spinner className="size-3.5" />Opening…</div>;
  else if (loaded.status === "error") body = presentation?.error?.({ message: loaded.message, missing: loaded.missing }) ?? <EmptyState icon={FileText} title="Could not open that file" description={loaded.message} tone="warn" />;
  else body = rendererBody;
  const shownActions = navActions?.key === key && ready ? navActions.actions : [];
  const columnPanel = openPanel && openPanel.content === "slot" && !fullscreen ? openPanel : null;
  const trailing = shownActions.length || panels.length ? <>
    {shownActions.map(({ id, label, hint, icon: Icon, disabled, active, onInvoke }) => <TooltipHint key={id} content={hint ?? label}><Button type="button" variant="ghost" size="icon-xs" className="size-6 text-muted-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground" aria-label={label} disabled={disabled} aria-pressed={active} onClick={() => { try { void Promise.resolve(onInvoke()).catch(error => onError?.(error)); } catch (error) { onError?.(error instanceof Error ? error : new Error(String(error))); } }}><Icon className="size-3.5" aria-hidden="true" /></Button></TooltipHint>)}
    {panels.map((panel) => <PanelToggle key={panel.id} id={panel.id} active={panel.id === openId} icon={panel.icon} label={panel.label} onClick={() => setPanel(nextOpenPanel(openId, panel.id))} />)}
  </> : null;
  // What the host can do with the file on screen: its ⋯ menu.
  const perform = host.fileActions?.perform;
  const fileMenu = useMemo(() => {
    const capabilities = new Set(Object.keys(perform ?? {}) as EntryAction[]);
    return capabilities.size ? {
      platform: host.fileActions?.platform ?? "linux", capabilities,
      onAction: (action: EntryAction, target: string) => { void Promise.resolve(perform?.[action]?.({ path: target, kind: "file" })).catch(error => onError?.(error)); },
    } : null;
  }, [perform, host.fileActions?.platform, onError]);
  // The name opens the explorer where the host's files can be browsed: a pick shows the file here.
  const explorer = useMemo(() => source.list && source.search ? { source, onOpen: (next: string) => onOpenFile(next) } : null, [source, onOpenFile]);
  // The logo's app menu: the host's links and the person's settings (Back to files is `onHome`).
  const menu = useMemo(() => host.links || appSettings?.length ? { links: host.links, appSettings, platform: appearance.platform } : null,
    [host.links, appSettings, appearance.platform]);
  // The navbar is drawn over every file, never over the host's home (which holds its menu itself)
  // or a view drawn small with no chrome (`compact`: an offscreen picture).
  const navbar = Boolean(path) && !appearance.compact && !fullscreen;
  return <ViewerMobileContext.Provider value={mobile}><ViewerHostContext.Provider value={host}><ViewerElementContext.Provider value={viewerElement}><div className="text-to-cad-file-viewer text-ui font-normal flex h-full min-h-0 min-w-0 flex-col overflow-hidden" ref={bindElement} data-viewer-layout={mobile ? "mobile" : "desktop"} tabIndex={-1}>
    {navbar ? <ViewerNavbar onHome={host.navigation.home} menu={menu} file={path} explorer={explorer} fileMenu={fileMenu} trailing={trailing} update={update} fullSize={fullSize} /> : null}
    <div ref={setBodyElement} className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden">
      <div className="min-w-0 flex-1 overflow-hidden">{body}</div>
      {columnPanel ? <FilePanelColumn mobile={mobile} portalContainer={bodyElement} onDismiss={() => setPanel("")} id={columnPanel.id} label={columnPanel.label} width={panelWidth} onWidthChange={changeWidth} onCollapse={collapsePanel}>
        <div className="h-full min-h-0" ref={setPanelSlot} />
      </FilePanelColumn> : null}
    </div>
  </div></ViewerElementContext.Provider></ViewerHostContext.Provider></ViewerMobileContext.Provider>;
}
