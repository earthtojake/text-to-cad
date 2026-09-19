import { Box, RefreshCw, Settings2 } from "lucide-react";
import { useEffect } from "react";
import { createCadClient } from "@hardcore/core/client";
import type { CadClient } from "@hardcore/core/client";
import type { PrepareContext, RendererViewProps } from "@hardcore/ui/file-viewer";
import { EmptyState } from "@hardcore/ui/navigation";
import { Button } from "@renderer/components/ui/button";
import { useUi } from "@renderer/state/ui";
import { subscribeSessionTabs } from "@renderer/state/explorer";
import type { ViewerOrigin } from "@shared/ipc/cad";
import type { ExplorerRoot, ExplorerTab, FileTab } from "@shared/types";

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
          try { answer = await window.hardcore.cad.viewerOrigin({ projectId, ...(root ? { root } : {}) }); }
          catch (error) { throw new CadRuntimeError({ origin: null, reason: "viewer-failed", message: error instanceof Error ? error.message : String(error) }); }
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
    window.addEventListener("beforeunload", () => { desktopConnections?.dispose(); desktopConnections = undefined; }, { once: true });
  }
  return desktopConnections.forTab(tab);
}

const TITLES: Record<NonNullable<ViewerOrigin["reason"]>, string> = {
  "runtime-not-ready": "The CAD runtime did not start",
  "viewer-failed": "The CAD viewer did not start",
  "no-project": "This file's project is no longer open",
};
const REASONS: Record<NonNullable<ViewerOrigin["reason"]>, string> = {
  "runtime-not-ready": "The Python runtime that ships with Hardcore could not run cadgen, so nothing can render this file. The runtime's own words are below.",
  "viewer-failed": "The runtime is fine, but its viewer process for this project did not come up. The launcher's last words are below.",
  "no-project": "Open the project again to render its files.",
};

export function DesktopCadFailure({ answer, onReady, reload }: { answer: ViewerOrigin } & Pick<RendererViewProps, "onReady" | "reload">) {
  const openSettings = useUi((state) => state.openSettings);
  useEffect(() => { onReady(false); }, [onReady]);
  const reason = answer.reason ?? "runtime-not-ready";
  return <EmptyState icon={Box} title={TITLES[reason]} description={REASONS[reason]} tone="warn" action={reason === "no-project" ? undefined :
    <div className="flex flex-col items-center gap-2" data-cad-failure={reason}>
      {answer.message ? <pre className="max-h-40 max-w-[420px] overflow-auto rounded-lg border bg-muted/40 px-3 py-2 text-left font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-muted-foreground"><code data-selectable>{answer.message}</code></pre> : null}
      {answer.log ? <p className="max-w-[420px] truncate text-[11px] text-muted-foreground" title={answer.log}>Log: <span data-selectable>{answer.log}</span></p> : null}
      <div className="flex items-center gap-2">
        <Button className="h-7 gap-1.5 text-xs" onClick={reload} size="sm" variant="secondary"><RefreshCw className="size-3.5" />Try again</Button>
        <Button className="h-7 gap-1.5 text-xs" onClick={() => openSettings("about")} size="sm" variant="ghost"><Settings2 className="size-3.5" />Runtime status</Button>
      </div>
    </div>} />;
}
