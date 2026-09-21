import { FileViewer } from "@hardcore/ui/file-viewer";
import type { ViewerHost } from "@hardcore/ui/host";
import { worktreeMark } from "@hardcore/ui/navigation";
import { GitBranch } from "lucide-react";
import { useCallback, useEffect, useMemo } from "react";
import { toast } from "sonner";
import { useResolvedTheme } from "@renderer/hooks/use-theme";
import { desktopLiveDocuments } from "@renderer/state/live-documents";
import { openSessionTab, readSessionStrip, selectSessionTab, updateSessionTab, useExplorer } from "@renderer/state/explorer";
import { useProjects } from "@renderer/state/projects";
import type { ExplorerRoot, Project } from "@shared/types";
import { createDesktopFileSource, createDesktopFileActions } from "./adapters/fileSource";
import { desktopClipboard } from "./host/clipboard";
import { createDesktopPromptContext } from "./host/promptContext";
import type { DesktopCadConnection } from "./adapters/cadRuntime";
import { useDesktopViewState } from "./adapters/persistence";
import { createDesktopRenderers } from "./renderers";

/** The desktop supplies a root, native services and tab navigation to the shared viewer. */
export function FileTab({ sessionId, tabId, project, root, path, panel, cadConnection }: {
  sessionId: string; tabId: string; project: Project; root: ExplorerRoot; path: string | null; panel: string | null;
  cadConnection?: DesktopCadConnection;
}) {
  const source = useMemo(() => createDesktopFileSource({ sessionId, projectId: project.id,
    projectName: () => useProjects.getState().projects.find(entry => entry.id === project.id)?.name ?? "Project", root }), [sessionId, project.id, root]);
  const composition = useMemo(() => createDesktopRenderers(project.id, root, tabId, cadConnection), [project.id, root, tabId, cadConnection]);
  useEffect(() => () => composition.dispose(), [composition]);
  const { state, onStateChange } = useDesktopViewState(source.id, tabId, root, panel);
  const reveal = useExplorer((state) => state.reveal);
  const colorScheme = useResolvedTheme();
  const promptContext = useMemo(() => createDesktopPromptContext(project.id, root, source.id, sessionId), [sessionId, project.id, root, source.id]);
  const fileActions = useMemo(() => createDesktopFileActions({ sessionId, projectId: project.id, root, sourceId: source.id, promptContext, clipboard: desktopClipboard }), [sessionId, project.id, root, source.id, promptContext]);
  const worktree = useMemo(() => worktreeMark(root), [root]);
  const onOpenFile = useCallback((next: string, options?: { target: "current" | "new" }) => {
    void (async () => {
      if (options?.target === "new") { await openSessionTab(sessionId, project.id, root, "file", { path: next }); return; }
      const strip = await readSessionStrip(sessionId);
      const existing = strip.tabs.find(tab => tab.kind === "file" && tab.path === next && tab.root === root);
      if (existing) { await selectSessionTab(sessionId, existing.id); return; }
      await updateSessionTab(sessionId, tabId, { path: next, panel: null });
    })().catch(error => toast.error(error instanceof Error ? error.message : String(error)));
  }, [sessionId, project.id, tabId, root]);
  const liveDocuments = useMemo(() => desktopLiveDocuments(tabId, { projectId: project.id, root }), [tabId, project.id, root]);
  const host = useMemo<ViewerHost>(() => ({
    ...liveDocuments, files: source, fileActions, clipboard: desktopClipboard, promptContext,
    navigation: { openFile: onOpenFile }, environment: { colorScheme, platform: fileActions.platform },
    lifecycle: { subscribeFlush(listener) {
      window.addEventListener("beforeunload", listener);
      return () => window.removeEventListener("beforeunload", listener);
    } },
  }), [source, fileActions, promptContext, onOpenFile, colorScheme, liveDocuments]);
  return <FileViewer file={path} host={host} renderers={composition.renderers} state={state} onStateChange={onStateChange}
    reveal={reveal?.root === root ? reveal : null}
    onError={(error) => toast.error(error.message)}
    leading={worktree ? <>
      <span className="flex shrink items-center gap-1 truncate rounded-sm px-0.5 text-muted-foreground" data-crumb="worktree" title={worktree.title}>
        <GitBranch aria-label="Worktree" className="size-3 shrink-0" /><span className="truncate">{worktree.label}</span>
      </span>
      {path ? <span className="shrink-0 text-muted-foreground/60" aria-hidden>›</span> : null}
    </> : null} />;
}
