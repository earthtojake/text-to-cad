import { Box, FolderOpen, RefreshCw, Settings2 } from "lucide-react";
import { useEffect } from "react";
import { toast } from "sonner";
import type { CadClient } from "@text-to-cad/core/client";
import type { PrepareContext, RendererViewProps } from "@text-to-cad/ui/file-viewer";
import { EmptyState } from "@text-to-cad/ui/navigation";
import { Button } from "@renderer/components/ui/button";
import { useUi } from "@renderer/state/ui";
import { subscribeSessionTabs } from "@renderer/state/explorer";
import { useRuntime } from "@renderer/state/runtime";
import type { ViewerOrigin } from "@shared/ipc/cad";
import type { ExplorerRoot, ExplorerTab, FileTab } from "@shared/types";
import { markViewerOpened } from "@renderer/state/onboarding";
import { errorMessage } from "@shared/ipc/errors";

export class CadRuntimeError extends Error {
  constructor(readonly answer: ViewerOrigin) { super(answer.message ?? "The CAD runtime did not start."); }
}

/** A root owns its connection; the Python process lifecycle remains in main. */
export function createDesktopCadConnection(projectId: string, root: ExplorerRoot) {
  let connection: CadClient | undefined;
  let connectionOrigin = "";
  let pending: Promise<CadClient> | undefined;
  let generation = 0;
  return {
    async acquire(context: PrepareContext): Promise<CadClient> {
      context.signal.throwIfAborted();
      if (!pending) {
        const requestedAt = generation;
        pending = (async () => {
          let answer: ViewerOrigin;
          try { answer = await window.textToCad.cad.viewerOrigin({ projectId, ...(root ? { root } : {}) }); }
          catch (error) { throw new CadRuntimeError({ origin: null, reason: "viewer-failed", message: errorMessage(error) }); }
          // The client reaches three.js through its tessellation cache (~2 MB), so
          // it loads with the first CAD file rather than with the window. A chunk
          // that does not load is a viewer that did not start, and the tab's
          // failure card says so rather than showing the loader's raw rejection.
          const { createCadClient } = await import("@text-to-cad/core/client").catch((error: unknown) => {
            throw new CadRuntimeError({ origin: null, reason: "viewer-failed", message: `The CAD viewer's code did not load: ${errorMessage(error)}` });
          });
          if (generation !== requestedAt) throw new DOMException("The operation was aborted.", "AbortError");
          if (!answer.origin) throw new CadRuntimeError(answer);
          // Main answers immediately for its live viewer, and can return a new
          // origin after a crash/restart. Keep warm state only for that origin.
          if (connection && connectionOrigin === answer.origin) return connection;
          connection?.dispose();
          connection = undefined;
          const client = createCadClient({ origin: answer.origin, workspaceId: context.source.id });
          connection = client;
          connectionOrigin = answer.origin;
          // A CAD file reached the viewer: the Getting started checklist's last item.
          markViewerOpened();
          // The viewer came up on a runtime whose status may carry a kernel
          // warning; hold it, so a STEP build that fails can say so. Main's
          // answer is the probe it already ran.
          void useRuntime.getState().load().catch(() => {});
          return client;
        })();
      }
      const request = pending;
      try { const client = await request; context.signal.throwIfAborted(); return client; }
      finally { if (pending === request) pending = undefined; }
    },
    dispose() { generation += 1; connection?.dispose(); connection = undefined; connectionOrigin = ""; pending = undefined; },
  };
}

export type DesktopCadConnection = Pick<ReturnType<typeof createDesktopCadConnection>, "acquire">;

/** Open file tabs share a root connection without keeping their viewports mounted. */
export function createDesktopCadConnections(projectId: string) {
  const connections = new Map<ExplorerRoot, ReturnType<typeof createDesktopCadConnection>>();
  const borrowers = new Map<ExplorerRoot, DesktopCadConnection>();
  return {
    forRoot(root: ExplorerRoot): DesktopCadConnection {
      let borrower = borrowers.get(root);
      if (!borrower) {
        borrower = {
          acquire(context) {
            context.signal.throwIfAborted();
            let connection = connections.get(root);
            if (!connection) {
              connection = createDesktopCadConnection(projectId, root);
              connections.set(root, connection);
            }
            return connection.acquire(context);
          },
        };
        borrowers.set(root, borrower);
      }
      return borrower;
    },
    retainRoots(roots: Iterable<ExplorerRoot>) {
      const retained = new Set(roots);
      for (const [root, connection] of connections) {
        if (retained.has(root)) continue;
        connection.dispose();
        connections.delete(root);
      }
      for (const root of borrowers.keys()) {
        if (!retained.has(root)) borrowers.delete(root);
      }
    },
    dispose() {
      for (const connection of connections.values()) connection.dispose();
      connections.clear();
      borrowers.clear();
    },
  };
}

type CadTabOwner = Pick<FileTab, "id" | "sessionId" | "projectId" | "root">;
type SubscribeTabs = (listener: (tabs: readonly ExplorerTab[]) => void) => () => void;

/**
 * Open tabs own warm root clients independently of the visible pane. Switching
 * sessions or collapsing the explorer releases the viewport, never the root's
 * bounded geometry caches. The final tab owner releases its client.
 */
export function createDesktopCadConnectionRegistry(subscribeTabs: SubscribeTabs = subscribeSessionTabs) {
  const projects = new Map<string, ReturnType<typeof createDesktopCadConnections>>();
  const borrowers = new Map<string, DesktopCadConnection>();
  let owners = new Map<string, CadTabOwner>();
  let disposed = false;
  const ownerKey = (tab: CadTabOwner) => JSON.stringify([tab.sessionId, tab.id, tab.projectId, tab.root]);
  const unsubscribe = subscribeTabs(tabs => {
    owners = new Map(tabs.filter((tab): tab is FileTab => tab.kind === "file").map(tab => [ownerKey(tab), tab]));
    const rootsByProject = new Map<string, Set<ExplorerRoot>>();
    for (const owner of owners.values()) {
      const roots = rootsByProject.get(owner.projectId) ?? new Set<ExplorerRoot>();
      roots.add(owner.root);
      rootsByProject.set(owner.projectId, roots);
    }
    for (const [projectId, connections] of projects) {
      const roots = rootsByProject.get(projectId);
      connections.retainRoots(roots ?? []);
      if (!roots) projects.delete(projectId);
    }
    for (const key of borrowers.keys()) {
      if (!owners.has(key)) borrowers.delete(key);
    }
  });
  return {
    forTab(tab: CadTabOwner): DesktopCadConnection {
      const key = ownerKey(tab);
      let borrower = borrowers.get(key);
      if (!borrower) {
        borrower = {
          acquire(context) {
            context.signal.throwIfAborted();
            if (disposed || !owners.has(key)) throw new DOMException("This file tab is closed.", "AbortError");
            let connections = projects.get(tab.projectId);
            if (!connections) {
              connections = createDesktopCadConnections(tab.projectId);
              projects.set(tab.projectId, connections);
            }
            return connections.forRoot(tab.root).acquire(context);
          },
        };
        borrowers.set(key, borrower);
      }
      return borrower;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      unsubscribe();
      for (const connections of projects.values()) connections.dispose();
      projects.clear(); borrowers.clear(); owners.clear();
    },
  };
}

let desktopConnections: ReturnType<typeof createDesktopCadConnectionRegistry> | undefined;

/** One registry for the renderer window; constructing it starts no CAD work. */
export function desktopCadConnectionForTab(tab: CadTabOwner): DesktopCadConnection {
  if (!desktopConnections) {
    desktopConnections = createDesktopCadConnectionRegistry();
    // `pagehide`, not `beforeunload`: an unload refused over unsaved drafts
    // (state/live-documents.ts) and then cancelled keeps this document and
    // every CAD tab in it alive.
    window.addEventListener("pagehide", () => { desktopConnections?.dispose(); desktopConnections = undefined; }, { once: true });
  }
  return desktopConnections.forTab(tab);
}

const TITLES: Record<NonNullable<ViewerOrigin["reason"]>, string> = {
  "runtime-not-ready": "The CAD runtime did not start",
  "viewer-failed": "The CAD viewer did not start",
  "no-project": "This file's project is no longer open",
};
const REASONS: Record<NonNullable<ViewerOrigin["reason"]>, string> = {
  "runtime-not-ready": "The Python runtime that ships with text-to-cad could not run cadgen, so nothing can render this file. The runtime's own words are below.",
  "viewer-failed": "The runtime is fine, but its viewer process for this project did not come up. The launcher's last words are below.",
  // Projects are derived from sessions — there is no "open project" to
  // point at. A session in the folder brings its root back.
  "no-project": "Select a session in this folder to render its files.",
};

/**
 * A failed build's recovery note when the runtime is ready with a CAD kernel
 * warning (`missing`, `unsupported`, `timeout`): the build may have failed for
 * that, in cadgen's words. `timedOut`: the check did not finish, so the next
 * step is to check again, not to change the source. Null when the kernel is
 * fine or the status is not known.
 */
export function runtimeKernelNote(): { note: string; timedOut: boolean } | null {
  const kernel = useRuntime.getState().status?.kernel;
  if (!kernel) return null;
  // `timeout` is not a verdict on the kernel: the check did not finish.
  return kernel.state === "timeout"
    ? { note: `The CAD runtime's kernel check did not finish (${kernel.message})`, timedOut: true }
    : { note: `The CAD runtime's kernel is ${kernel.state}, which can stop a STEP build: ${kernel.message}`, timedOut: false };
}

/** The runtime log, shown in the file manager; main names the file. */
function revealLog() {
  void window.textToCad.runtime.revealLog()
    .then(({ revealed }) => { if (!revealed) toast.error("There is no runtime log yet."); })
    .catch((error: unknown) => toast.error(errorMessage(error)));
}

/**
 * The runtime that failed is the person's own when an override names it (`CAD_DESKTOP_PYTHON`, or
 * the `cadPythonOverride` setting): the one that ships with the app was never asked, so the card
 * names the override's path rather than blaming the bundle.
 */
function overrideReason(python: string): string {
  return `The override interpreter at ${python} could not run cadgen, so nothing can render this file. It comes from CAD_DESKTOP_PYTHON or the cadPythonOverride setting (Runtime status shows which); without it, the runtime that ships with text-to-cad is used. Its own words are below.`;
}

export function DesktopCadFailure({ answer, onReady, reload }: { answer: ViewerOrigin } & Pick<RendererViewProps, "onReady" | "reload">) {
  const openSettings = useUi((state) => state.openSettings);
  const runtime = useRuntime((state) => state.status);
  useEffect(() => { onReady(false); }, [onReady]);
  const reason = answer.reason ?? "runtime-not-ready";
  // Which interpreter failed is the runtime status's to say; main answers from the probe it ran.
  useEffect(() => {
    if (reason === "runtime-not-ready") void useRuntime.getState().load().catch(() => {});
  }, [reason]);
  // The runtime probe remembers a failure for a minute, and `reload` only asks the viewer again —
  // which reads that cached rejection. A runtime card's Try again forgets the probe first (what
  // Settings › About › Repair does), so a fixed override or a reinstalled bundle is seen at once.
  const retry = () => {
    if (reason !== "runtime-not-ready") return reload();
    void useRuntime.getState().repair().catch(() => {}).finally(reload);
  };
  const override = reason === "runtime-not-ready" && runtime?.source === "override" && runtime.state !== "ready" && runtime.python ? runtime.python : null;
  return <EmptyState icon={Box} title={TITLES[reason]} description={override ? overrideReason(override) : REASONS[reason]} tone="warn" action={reason === "no-project" ?
    <div className="flex items-center gap-2" data-cad-failure={reason}>
      <Button className="h-7 gap-1.5 text-xs" onClick={reload} size="sm" variant="secondary"><RefreshCw className="size-3.5" />Try again</Button>
    </div> :
    <div className="flex flex-col items-center gap-2" data-cad-failure={reason}>
      {answer.message ? <pre className="max-h-40 max-w-[420px] overflow-auto rounded-lg border bg-muted/40 px-3 py-2 text-left font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-muted-foreground"><code data-selectable>{answer.message}</code></pre> : null}
      <div className="flex items-center gap-2">
        <Button className="h-7 gap-1.5 text-xs" onClick={retry} size="sm" variant="secondary"><RefreshCw className="size-3.5" />Try again</Button>
        <Button className="h-7 gap-1.5 text-xs" onClick={() => openSettings("about")} size="sm" variant="ghost"><Settings2 className="size-3.5" />Runtime status</Button>
        {answer.log ? <Button className="h-7 gap-1.5 text-xs" onClick={revealLog} size="sm" variant="ghost"><FolderOpen className="size-3.5" />Reveal log</Button> : null}
      </div>
    </div>} />;
}
