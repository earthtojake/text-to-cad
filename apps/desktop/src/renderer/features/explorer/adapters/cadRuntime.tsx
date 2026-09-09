import { Box, RefreshCw, Settings2 } from "lucide-react";
import { useEffect } from "react";
import { createCadClient } from "@hardcore/core/client";
import type { CadClient } from "@hardcore/core/client";
import type { PrepareContext, RendererViewProps } from "@hardcore/ui/file-viewer";
import { EmptyState } from "@hardcore/ui/navigation";
import { Button } from "@renderer/components/ui/button";
import { useUi } from "@renderer/state/ui";
import type { ViewerOrigin } from "@shared/ipc/cad";
import type { ExplorerRoot } from "@shared/types";

export class CadRuntimeError extends Error {
  constructor(readonly answer: ViewerOrigin) { super(answer.message ?? "The CAD runtime did not start."); }
}

/** The tab owns its connection; the Python process lifecycle remains in main. */
export function createDesktopCadConnection(projectId: string, root: ExplorerRoot) {
  let connection: CadClient | undefined;
  let pending: Promise<CadClient> | undefined;
  let generation = 0;
  return {
    async acquire(context: PrepareContext): Promise<CadClient> {
      context.signal.throwIfAborted();
      if (connection) return connection;
      if (!pending) {
        const requestedAt = generation;
        pending = (async () => {
          let answer: ViewerOrigin;
          try { answer = await window.hardcore.cad.viewerOrigin({ projectId, ...(root ? { root } : {}) }); }
          catch (error) { throw new CadRuntimeError({ origin: null, reason: "viewer-failed", message: error instanceof Error ? error.message : String(error) }); }
          if (!answer.origin) throw new CadRuntimeError(answer);
          const client = createCadClient({ origin: answer.origin, workspaceId: context.source.id });
          if (generation !== requestedAt) { client.dispose(); throw new DOMException("The operation was aborted.", "AbortError"); }
          connection = client;
          return client;
        })();
      }
      const request = pending;
      try { const client = await request; context.signal.throwIfAborted(); return client; }
      finally { if (pending === request) pending = undefined; }
    },
    dispose() { generation += 1; connection?.dispose(); connection = undefined; pending = undefined; },
  };
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
