import { TooltipHint } from "@hardcore/ui/primitives/tooltip";
import { FileText, RotateCw } from "lucide-react";
import { Component, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Button } from "../primitives/button.jsx";
import { Spinner } from "../primitives/spinner.js";
import { buildCrumbs, clampPanelWidth, EmptyState, FILE_PANEL_TREE, FileNavRow, FilePanelColumn, FileTree, nextOpenPanel, PanelToggle, PANEL_DEFAULT_WIDTH, PANEL_MIN_WIDTH, resolveOpenPanel, treePanel, useElementWidth } from "./navigation/index.js";
import { useFileDocument } from "./hooks/useFileDocument.js";
import { useFileNavigation } from "./hooks/useFileNavigation.js";
import type { FileNavigationAction, FileViewerProps, JsonValue, FileViewerState } from "./types.js";
import { ViewerMobileContext, VIEWER_MOBILE_BREAKPOINT } from "./responsive.js";
import { ViewerElementContext, ViewerHostContext } from '../host/context.js';
import { useLiveDocument } from '../host/useLiveDocument.js';
import { useViewerCommands } from '../host/useViewerCommands.js';

class RenderBoundary extends Component<{ children: ReactNode; onError?: (error: Error) => void }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, _info: ErrorInfo) { this.props.onError?.(error); }
  render() { return this.state.error ? <EmptyState icon={FileText} title="Could not display that file" description={this.state.error.message} tone="warn" /> : this.props.children; }
}

/** The complete file tab. Its only knowledge of formats comes from registrations. */
export function FileViewer({ file, host, renderers, state, onStateChange, leading, navigationActions, displayActions, navigationPath, narrowCrumbs, reveal, onError, presentation, fullscreen = false, onFullscreenChange }: FileViewerProps) {
  const source = host.files;
  const onOpenFile = host.navigation.openFile;
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
  const [rootRef, paneWidth] = useElementWidth();
  const mobile = paneWidth > 0 && paneWidth < VIEWER_MOBILE_BREAKPOINT;
  // Mobile sheets are deliberate, temporary openings. Keep the desktop panel preference intact.
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
  useViewerCommands({ host, generation: key, path, document, reload, element: viewerElement });
  const [navigationStatusSlot, setNavigationStatusSlot] = useState<HTMLDivElement | null>(null);
  const [panelVisibility, setPanelVisibility] = useState<{ key: string; visible: boolean } | null>(null);
  const onPanelVisibilityChange = useCallback((visible: boolean) => { if (currentKey.current === key) setPanelVisibility(previous => previous?.key === key && previous.visible === visible ? previous : { key, visible }); }, [key]);
  const [panelSlot, setPanelSlot] = useState<HTMLDivElement | null>(null);
  const [readiness, setReadiness] = useState<{ key: string; ready: boolean } | null>(null);
  const [chrome, setChrome] = useState<{ key: string; visible: boolean } | null>(null);
  const [navActions, setNavActions] = useState<{ key: string; actions: readonly FileNavigationAction[] } | null>(null);
  const onNavigationActionsChange = useCallback((actions: readonly FileNavigationAction[]) => { if (currentKey.current === key) setNavActions({ key, actions }); }, [key]);
  const onReady = useCallback((ready: boolean) => { if (currentKey.current === key) setReadiness((previous) => previous?.key === key && previous.ready === ready ? previous : { key, ready }); }, [key]);
  const onChromeVisibilityChange = useCallback((visible: boolean) => { if (currentKey.current === key) setChrome((previous) => previous?.key === key && previous.visible === visible ? previous : { key, visible }); }, [key]);
  // Fullscreen is the host's to give and a renderer's to take: only one that declares it is
  // handed the host's switch, and a file that has none leaves the host's fullscreen.
  const fullscreenAvailable = Boolean(onFullscreenChange) && loaded.status === "ready" && loaded.renderer.fullscreen === true;
  const presenting = fullscreen && fullscreenAvailable;
  const panelsVisible = !presenting && (panelVisibility?.key === key ? panelVisibility.visible : true);
  useEffect(() => { if (fullscreen && loaded.status === "ready" && !fullscreenAvailable) onFullscreenChange?.(false); }, [fullscreen, loaded.status, fullscreenAvailable, onFullscreenChange]);
  const chromeVisible = chrome?.key === key ? chrome.visible : true;
  const ready = loaded.status === "ready" && (readiness?.key === key ? readiness.ready : true);
  const declared = (open: string) => loaded.status === "ready" ? loaded.prepared.panels?.({ open, ready, file: loaded.file }) ?? [] : [];
  const panelsAt = (open: string) => [...declared(open), ...(source.list ? [treePanel(open, { empty: loaded.status === "empty" })] : [])];
  const requestedPanel = mobile ? mobilePanel : state.panel;
  const openId = resolveOpenPanel(panelsAt(requestedPanel ?? ""), requestedPanel)?.id ?? "";
  const panels = panelsAt(openId);
  const openPanel = panels.find((panel) => panel.id === openId);
  const collapsePanel = useCallback(() => changeState(previous => ({ ...previous, panel: "", panelWidth: PANEL_DEFAULT_WIDTH })), [changeState]);
  const panelWidth = Math.min(clampPanelWidth(state.panelWidth), paneWidth > PANEL_MIN_WIDTH ? paneWidth - 1 : Infinity);
  useEffect(() => {
    if (!mobile && chromeVisible && openPanel && openPanel.content !== "body" && paneWidth > 0 && paneWidth <= PANEL_MIN_WIDTH) collapsePanel();
  }, [mobile, chromeVisible, openId, openPanel?.content, paneWidth, collapsePanel]);
  const crumbs = useMemo(() => {
    const all = buildCrumbs({ path: selectedPath, narrow: mobile ? false : (narrowCrumbs ?? false) });
    return mobile ? all.slice(-1) : all;
  }, [selectedPath, mobile, narrowCrumbs]);
  const rendererStateKey = loaded.status === "ready" ? JSON.stringify([loaded.file.path, loaded.renderer.id]) : "";
  // A departing renderer flushes its last per-file state during unmount. That
  // write belongs to its own key even after another file in this root opens.
  const setRendererState = useCallback((value: JsonValue) => { if (latest.current.sourceId === source.id && rendererStateKey) changeState((previous) => ({ ...previous, renderers: { ...previous.renderers, [rendererStateKey]: value } })); }, [changeState, rendererStateKey, source.id]);

  let body: ReactNode;
  if (loaded.status === "empty") body = presentation?.empty ?? <EmptyState icon={FileText} title="No file open" description={source.list ? "Pick one from the tree on the right, or filter by name." : "Choose a file to open."} />;
  else if (loaded.status === "loading") body = presentation?.loading ?? <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground" role="status"><Spinner className="size-3.5" />Opening…</div>;
  else if (loaded.status === "error") body = presentation?.error?.(loaded.message) ?? <EmptyState icon={FileText} title="Could not open that file" description={loaded.message} tone="warn" />;
  else {
    const Renderer = loaded.prepared.Component;
    body = <RenderBoundary key={key} onError={onError}><Renderer displayActions={displayActions} key={key} file={loaded.file} source={source} document={document}
      navigationStatusSlot={navigationStatusSlot} onPanelVisibilityChange={onPanelVisibilityChange}
      openPanel={openId} panelSlot={panelSlot} onPanelOpen={setPanel} onReady={onReady} onChromeVisibilityChange={onChromeVisibilityChange}
      fullscreen={presenting} onFullscreenChange={fullscreenAvailable ? onFullscreenChange : undefined} onNavigationActionsChange={onNavigationActionsChange}
      onOpenFile={(next, options) => onOpenFile(next, options ?? { target: "new" })} appearance={appearance}
      state={state.renderers?.[rendererStateKey]} onStateChange={setRendererState} reload={reload} /></RenderBoundary>;
  }
  return <ViewerMobileContext.Provider value={mobile}><ViewerHostContext.Provider value={host}><ViewerElementContext.Provider value={viewerElement}><div className="hardcore-file-viewer text-ui font-normal flex h-full min-h-0 min-w-0 flex-col overflow-hidden" ref={bindElement} data-viewer-layout={mobile ? "mobile" : "desktop"} tabIndex={-1} data-source-id={source.id}>
    {chromeVisible ? <FileNavRow activePath={selectedPath} crumbs={crumbs} leading={leading} onOpen={(next) => onOpenFile(next, { target: "current" })} source={navigation.crumbs}
      status={<>{document?.dirty ? <TooltipHint content="Unsaved changes"><span aria-label="Unsaved changes"  className="ml-1 size-1.5 shrink-0 rounded-full bg-foreground/60" /></TooltipHint> : null}<div ref={setNavigationStatusSlot} className={mobile ? "ml-1 shrink-0" : "ml-2 min-w-0 overflow-hidden"} data-file-navigation-status="" /></>}
      trailing={<>{navigationActions}{navActions?.key === key && ready ? navActions.actions.map(({ id, label, icon: Icon, disabled, active, onInvoke }) => <TooltipHint key={id} content={label === "Take snapshot" ? "Snapshot" : label}><Button  type="button" variant="ghost" size="icon-xs" className="size-6 text-muted-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground" aria-label={label}  disabled={disabled} aria-pressed={active} data-file-action={id} onClick={() => { try { void Promise.resolve(onInvoke()).catch(error => onError?.(error)); } catch (error) { onError?.(error instanceof Error ? error : new Error(String(error))); } }}><Icon className="size-3.5" aria-hidden="true" /></Button></TooltipHint>) : null}{panels.map((panel) => <PanelToggle key={panel.id} id={panel.id} disabled={!panelsVisible} active={panelsVisible && panel.id === openId} icon={panel.icon} label={panel.label} onClick={() => setPanel(nextOpenPanel(openId, panel.id))} testId={panel.id === FILE_PANEL_TREE ? "tree-toggle" : undefined} />)}</>} /> : null}
    {chromeVisible && document?.stale ? <div className="flex shrink-0 items-center gap-2 border-b bg-amber-500/10 px-3 py-1.5 text-[12px] text-amber-700 dark:text-amber-400" role="status">
      <RotateCw className="size-3.5 shrink-0" /><span className="flex-1">This file changed on disk since you opened it.</span>
      <Button className="h-6 px-2 text-[12px] font-normal" onClick={document.reload} size="sm" variant="secondary">Reload</Button>
      <Button className="h-6 px-2 text-[12px] font-normal" onClick={document.keepMine} size="sm" variant="ghost">Keep mine</Button>
    </div> : null}
    {chromeVisible && document?.error ? <div className="flex shrink-0 items-center gap-2 border-b bg-destructive/10 px-3 py-1.5 text-[12px] text-destructive" role="alert">
      <span className="flex-1">Could not save: {document.error}</span><Button className="h-6 px-2 text-[12px] font-normal" size="sm" variant="secondary" onClick={() => void document.save()}>Try again</Button>
    </div> : null}
    <div data-file-viewer-body="" ref={setBodyElement} className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden">
      <div className="min-w-0 flex-1 overflow-hidden">{body}</div>
      {chromeVisible && openPanel && openPanel.content !== "body" ? <FilePanelColumn mobile={mobile} portalContainer={bodyElement} onDismiss={() => setPanel("")} hidden={!panelsVisible} id={openPanel.id} label={openPanel.label} width={panelWidth} onWidthChange={(nextWidth) => changeState((previous) => ({ ...previous, panelWidth: clampPanelWidth(nextWidth) }))} onCollapse={collapsePanel}>
        {openPanel.content === "tree" ? <FileTree key={source.id} source={navigation.tree} activePath={selectedPath} edit={navigation.edit} reveal={reveal} onOpen={(next) => { if (mobile) setMobilePanel(""); onOpenFile(next, { target: "new", panel: FILE_PANEL_TREE }); }} /> : <div className="h-full min-h-0" ref={setPanelSlot} />}
      </FilePanelColumn> : null}
    </div>
  </div></ViewerElementContext.Provider></ViewerHostContext.Provider></ViewerMobileContext.Provider>;
}
