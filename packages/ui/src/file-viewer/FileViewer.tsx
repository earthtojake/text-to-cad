import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { FileText } from "lucide-react";
import { isDocumentId } from "@text-to-cad/core/lib/cadRefs.js";
import { Component, useCallback, useMemo, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Button } from "../primitives/button.jsx";
import { Spinner } from "../primitives/spinner.js";
import { EmptyState, ViewerNavbar } from "./navigation/index.js";
import type { EntryAction } from "./navigation/index.js";
import { useFileDocument } from "./hooks/useFileDocument.js";
import type { FileNavigationAction, FileViewerProps, JsonValue, FileViewerState } from "./types.js";
import { ViewerMobileContext, useViewerMobileMeasure } from "./responsive.js";
import { ViewerElementContext, ViewerHostContext } from '../host/context.js';
import { I18nProvider, translator } from "../i18n/index.js";

class RenderBoundary extends Component<{ children: ReactNode; title: string; onError?: (error: Error) => void }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, _info: ErrorInfo) { this.props.onError?.(error); }
  render() { return this.state.error ? <EmptyState icon={FileText} title={this.props.title} description={this.state.error.message} tone="warn" /> : this.props.children; }
}

/**
 * The complete file view: one file, by its absolute path, under the one navbar. Its only knowledge
 * of formats comes from registrations. With no file it shows the host's home.
 */
export function FileViewer({ file, host, renderers, state, onStateChange, colorScheme, language, appSettings, update, fullSize, openInBrowser, history, notice, navbarActions, overlay, onError, presentation }: FileViewerProps) {
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

  // Width matters only as the breakpoint: this state changes when it is crossed, never per pixel.
  const [rootRef, mobile] = useViewerMobileMeasure();
  const viewerElement = useRef<HTMLDivElement | null>(null);
  const bindElement = useCallback((element: HTMLDivElement | null) => { viewerElement.current = element; rootRef(element); }, [rootRef]);
  // The navbar's box the renderer draws its view controls into (`navbarSlot`).
  const [navbarSlot, setNavbarSlot] = useState<HTMLDivElement | null>(null);
  const [readiness, setReadiness] = useState<{ key: string; ready: boolean } | null>(null);
  const [navActions, setNavActions] = useState<{ key: string; actions: readonly FileNavigationAction[] } | null>(null);
  const onNavigationActionsChange = useCallback((actions: readonly FileNavigationAction[]) => { if (currentKey.current === key) setNavActions({ key, actions }); }, [key]);
  const onReady = useCallback((ready: boolean) => { if (currentKey.current === key) setReadiness((previous) => previous?.key === key && previous.ready === ready ? previous : { key, ready }); }, [key]);
  const ready = loaded.status === "ready" && (readiness?.key === key ? readiness.ready : true);
  const rendererStateKey = loaded.status === "ready" ? JSON.stringify([loaded.file.path, loaded.renderer.id]) : "";
  // A departing renderer flushes its last per-file state during unmount. That write belongs to its
  // own key even after another file opens; whether it is kept is the host's (`CadViewer` keeps the
  // file on screen's alone, and drops this one once it has landed).
  const setRendererState = useCallback((value: JsonValue) => { if (latest.current.sourceId === source.id && rendererStateKey) changeState((previous) => ({ ...previous, renderers: { ...previous.renderers, [rendererStateKey]: value } })); }, [changeState, rendererStateKey, source.id]);

  // The renderer is re-rendered only when what it is handed changes: not by a navbar action it
  // published, a resize within one layout, or anything else this frame redraws for itself. Its
  // `state` is the record as it stood when this renderer opened the file: what it saves after that
  // is its own and does not come back to it, so a save never re-renders the view that made it.
  const openedState = useRef<{ key: unknown; value: JsonValue | undefined }>({ key: undefined, value: undefined });
  const openedKey = `${String(key)}\u0000${rendererStateKey}`;
  if (openedState.current.key !== openedKey) openedState.current = { key: openedKey, value: state.renderers?.[rendererStateKey] };
  const rendererState = openedState.current.value;
  const shown = loaded.status === "ready" ? loaded : null;
  const rendererBody = useMemo(() => {
    if (!shown) return null;
    const Renderer = shown.prepared.Component;
    return <RenderBoundary key={key} title={t("file.displayFailed")} onError={onError}><Renderer notice={notice} key={key} file={shown.file} source={source}
      navbarSlot={navbarSlot} onReady={onReady} onNavigationActionsChange={onNavigationActionsChange}
      onOpenFile={onOpenFile} appearance={appearance}
      state={rendererState} onStateChange={setRendererState} reload={reload} /></RenderBoundary>;
  }, [shown, key, onError, notice, source, navbarSlot, onReady,
    onNavigationActionsChange, onOpenFile, appearance, rendererState, setRendererState, reload, t]);

  let body: ReactNode;
  if (loaded.status === "empty") body = presentation?.home ?? null;
  else if (loaded.status === "loading") body = presentation?.loading ?? <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground" role="status"><Spinner className="size-3.5" />{t("file.opening")}</div>;
  else if (loaded.status === "error") body = presentation?.error?.({ message: loaded.message, missing: loaded.missing, reload: reloadCurrent }) ?? <EmptyState icon={FileText} title={t("file.openFailed")} description={loaded.message} tone="warn" />;
  else body = rendererBody;
  const shownActions = navActions?.key === key && ready ? navActions.actions : [];
  const trailing = shownActions.length ? <>
    {shownActions.map(({ id, label, hint, icon: Icon, disabled, active, onInvoke }) => <TooltipHint key={id} content={hint ?? label}><Button type="button" variant="ghost" size="icon-xs" className="size-6 text-muted-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground" aria-label={label} disabled={disabled} aria-pressed={active} onClick={() => { try { void Promise.resolve(onInvoke()).catch(error => onError?.(error)); } catch (error) { onError?.(error instanceof Error ? error : new Error(String(error))); } }}><Icon className="size-3.5" aria-hidden="true" /></Button></TooltipHint>)}
  </> : null;
  // The on-disk file the view browses from and acts on: the file's own path, or none for a document
  // with no file of its own (a model's, by its id): it has no Select File and no file menu.
  const navigationPath = shown ? (shown.file.navigationPath === undefined ? shown.file.path : shown.file.navigationPath)
    : path && !isDocumentId(path) ? path : null;
  // What the host can do with the file on screen: its ⋯ menu.
  const perform = host.fileActions?.perform;
  const fileMenu = useMemo(() => {
    const capabilities = new Set(Object.keys(perform ?? {}) as EntryAction[]);
    return navigationPath && capabilities.size ? {
      platform: host.fileActions?.platform ?? "linux", capabilities,
      onAction: (action: EntryAction, target: string) => { void Promise.resolve(perform?.[action]?.({ path: target, kind: "file" })).catch(error => onError?.(error)); },
    } : null;
  }, [navigationPath, perform, host.fileActions?.platform, onError]);
  // The name opens the explorer -- Select File, rooted at the file's folder -- where the host's files
  // can be browsed and this view shows another: a pick shows the file here. A view that shows its
  // file alone opens none, and nor does a document with no file of its own.
  const explorer = useMemo(() => navigationPath && source.list && source.search && onOpenFile ? { source, onOpen: onOpenFile } : null,
    [navigationPath, source, onOpenFile]);
  // The logo's app menu: the host's links and the person's settings (Back to files is `onHome`).
  const menu = useMemo(() => host.links || appSettings?.length || colorScheme || language ? { links: host.links, appSettings, colorScheme, language, platform: appearance.platform } : null,
    [host.links, appSettings, colorScheme, language, appearance.platform]);
  // The navbar is drawn over every file and over the host's home — there only the logo's menu (no
  // Back to files), Back and Forward where the host keeps the view's history, and the host's update,
  // Full size and Open in browser, each where it is over a file — never over a view drawn small with no chrome
  // (`compact`: an offscreen picture).
  const home = loaded.status === "empty" && Boolean(presentation?.home);
  const navbar = (Boolean(path) || home) && !appearance.compact;
  return <I18nProvider locale={locale}><ViewerMobileContext.Provider value={mobile}><ViewerHostContext.Provider value={host}><ViewerElementContext.Provider value={viewerElement}><div className="text-to-cad-file-viewer text-ui font-normal flex h-full min-h-0 min-w-0 flex-col overflow-hidden" ref={bindElement} data-viewer-layout={mobile ? "mobile" : "desktop"} tabIndex={-1}>
    {navbar ? (path
      ? <ViewerNavbar onHome={host.navigation.home} menu={menu} history={history} file={navigationPath ?? path} name={shown?.file.name} explorer={explorer} fileMenu={fileMenu} trailing={trailing} actions={navbarActions} update={update} fullSize={fullSize} openInBrowser={openInBrowser} controlsRef={setNavbarSlot} />
      : <ViewerNavbar menu={menu} history={history} actions={navbarActions} update={update} fullSize={fullSize} openInBrowser={openInBrowser} />) : null}
    <div className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden">
      <div className="min-w-0 flex-1 overflow-hidden">{body}</div>
      {overlay}
    </div>
  </div></ViewerElementContext.Provider></ViewerHostContext.Provider></ViewerMobileContext.Provider></I18nProvider>;
}
