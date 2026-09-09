import { FileText, RotateCw } from "lucide-react";
import { Component, useCallback, useMemo, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Button } from "../primitives/button.jsx";
import { Spinner } from "../primitives/spinner.js";
import { buildCrumbs, clampPanelWidth, EmptyState, FILE_PANEL_TREE, FileNavRow, FilePanelColumn, FileTree, nextOpenPanel, PanelToggle, resolveOpenPanel, treePanel, useElementWidth } from "./navigation/index.js";
import { useFileDocument } from "./hooks/useFileDocument.js";
import { useFileNavigation } from "./hooks/useFileNavigation.js";
import type { FileActivity, FileViewerProps, JsonValue, FileViewerState } from "./types.js";

class RenderBoundary extends Component<{ children: ReactNode; onError?: (error: Error) => void }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, _info: ErrorInfo) { this.props.onError?.(error); }
  render() { return this.state.error ? <EmptyState icon={FileText} title="Could not display that file" description={this.state.error.message} tone="warn" /> : this.props.children; }
}

/** The complete file tab. Its only knowledge of formats comes from registrations. */
export function FileViewer({ file, source, renderers, state, onStateChange, onOpenFile, appearance = { colorScheme: "light" }, leading, navigationPath, narrowCrumbs, reveal, onError, presentation }: FileViewerProps) {
  const session = useFileDocument(file, source, renderers);
  const { loaded, document, key, path, reload } = session;
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
  const setPanel = useCallback((panel: string) => { if (currentKey.current === key) changeState((previous) => ({ ...previous, panel })); }, [changeState, key]);
  const navigation = useFileNavigation({ source, state, onStateChange, onOpenFile, path: selectedPath, onError });
  const [rootRef, paneWidth] = useElementWidth();
  const [panelSlot, setPanelSlot] = useState<HTMLDivElement | null>(null);
  const [readiness, setReadiness] = useState<{ key: string; ready: boolean } | null>(null);
  const [chrome, setChrome] = useState<{ key: string; visible: boolean } | null>(null);
  const [activity, setActivity] = useState<{ key: string; value: FileActivity | null } | null>(null);
  const onReady = useCallback((ready: boolean) => { if (currentKey.current === key) setReadiness((previous) => previous?.key === key && previous.ready === ready ? previous : { key, ready }); }, [key]);
  const onChromeVisibilityChange = useCallback((visible: boolean) => { if (currentKey.current === key) setChrome((previous) => previous?.key === key && previous.visible === visible ? previous : { key, visible }); }, [key]);
  const onActivityChange = useCallback((value: FileActivity | null) => { if (currentKey.current === key) setActivity((previous) => previous?.key === key && previous.value === value ? previous : { key, value }); }, [key]);
  const chromeVisible = chrome?.key === key ? chrome.visible : true;
  const ready = loaded.status === "ready" && (readiness?.key === key ? readiness.ready : true);
  const declared = (open: string) => loaded.status === "ready" ? loaded.renderer.panels?.({ open, ready, file: loaded.file }) ?? [] : [];
  const panelsAt = (open: string) => [...declared(open), ...(source.list ? [treePanel(open)] : [])];
  const openId = resolveOpenPanel(panelsAt(state.panel ?? ""), state.panel)?.id ?? "";
  const panels = panelsAt(openId);
  const openPanel = panels.find((panel) => panel.id === openId);
  const panelWidth = clampPanelWidth(state.panelWidth);
  const width = chromeVisible && openPanel && openPanel.content !== "body" ? panelWidth : 0;
  const crumbs = useMemo(() => buildCrumbs({ path: selectedPath, narrow: narrowCrumbs ?? (paneWidth > 0 && paneWidth - width < 720) }), [selectedPath, paneWidth, width, narrowCrumbs]);
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
    body = <RenderBoundary key={key} onError={onError}><Renderer key={key} file={loaded.file} source={source} document={document}
      openPanel={openId} panelSlot={panelSlot} onPanelOpen={setPanel} onReady={onReady} onChromeVisibilityChange={onChromeVisibilityChange}
      onActivityChange={onActivityChange}
      onOpenFile={(next) => onOpenFile(next, { target: "new" })} appearance={appearance}
      state={state.renderers?.[rendererStateKey]} onStateChange={setRendererState} reload={reload} /></RenderBoundary>;
  }
  return <div className="hardcore-file-viewer flex h-full min-h-0 flex-col" ref={rootRef} data-source-id={source.id}>
    {chromeVisible ? <FileNavRow activePath={selectedPath} crumbs={crumbs} leading={leading} onOpen={(next) => onOpenFile(next, { target: "current" })} source={navigation.crumbs}
      status={<>{document?.dirty ? <span aria-label="Unsaved changes" title="Unsaved changes" className="ml-1 size-1.5 shrink-0 rounded-full bg-foreground/60" /> : null}{presentation?.activity?.(activity?.key === key ? activity.value : null)}</>}
      trailing={panels.map((panel) => <PanelToggle key={panel.id} id={panel.id} active={panel.id === openId} icon={panel.icon} label={panel.label} onClick={() => setPanel(nextOpenPanel(openId, panel.id))} testId={panel.id === FILE_PANEL_TREE ? "tree-toggle" : undefined} />)} /> : null}
    {document?.stale ? <div className="flex shrink-0 items-center gap-2 border-b bg-amber-500/10 px-3 py-1.5 text-[12px] text-amber-700 dark:text-amber-400" role="status">
      <RotateCw className="size-3.5 shrink-0" /><span className="flex-1">This file changed on disk since you opened it.</span>
      <Button className="h-6 px-2 text-[12px] font-medium" onClick={document.reload} size="sm" variant="secondary">Reload</Button>
      <Button className="h-6 px-2 text-[12px] font-medium" onClick={document.keepMine} size="sm" variant="ghost">Keep mine</Button>
    </div> : null}
    {document?.error ? <div className="flex shrink-0 items-center gap-2 border-b bg-destructive/10 px-3 py-1.5 text-[12px] text-destructive" role="alert">
      <span className="flex-1">Could not save: {document.error}</span><Button className="h-6 px-2 text-[12px] font-medium" size="sm" variant="secondary" onClick={() => void document.save()}>Try again</Button>
    </div> : null}
    <div className="relative flex min-h-0 flex-1">
      <div className="min-w-0 flex-1 overflow-hidden">{body}</div>
      {chromeVisible && openPanel && openPanel.content !== "body" ? <FilePanelColumn id={openPanel.id} label={openPanel.label} width={panelWidth} onWidthChange={(nextWidth) => changeState((previous) => ({ ...previous, panelWidth: clampPanelWidth(nextWidth) }))}>
        {openPanel.content === "tree" ? <FileTree key={source.id} source={navigation.tree} activePath={selectedPath} edit={navigation.edit} reveal={reveal} onOpen={(next) => onOpenFile(next, { target: "new" })} /> : <div className="h-full min-h-0" ref={setPanelSlot} />}
      </FilePanelColumn> : null}
    </div>
  </div>;
}
