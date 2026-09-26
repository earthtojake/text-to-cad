import { FileViewer } from "@hardcore/ui/file-viewer";
import type { ViewerHost } from "@hardcore/ui/host";
import { TooltipHint } from "@hardcore/ui/primitives/tooltip";
import { GitBranch } from "lucide-react";
import { useCallback, useEffect, useMemo } from "react";
import { toast } from "sonner";
import { useResolvedTheme } from "@renderer/hooks/use-theme";
import { desktopLiveDocuments } from "@renderer/state/live-documents";
import { openSessionTab, readSessionStrip, updateSessionTab, useExplorer } from "@renderer/state/explorer";
import { useProjects } from "@renderer/state/projects";
import { useSettings } from "@renderer/state/settings";
import type { ExplorerRoot, Project } from "@shared/types";
import { createDesktopFileSource, createDesktopFileActions } from "./adapters/fileSource";
import { desktopClipboard } from "./host/clipboard";
import { createDesktopPromptContext } from "./host/promptContext";
import type { DesktopCadConnection } from "./adapters/cadRuntime";
import { useDesktopViewState } from "./adapters/persistence";
import { createDesktopRenderers } from "./renderers";

/**
 * The worktree a tab's root is, drawn before the crumbs, or null for a tab in the project
 * directory. Not a crumb: it names the root, and a root has no menu — its neighbours are
 * outside the project. Which copy of the tree a file is in is the one thing its name does not say.
 */
export function worktreeMark(root: ExplorerRoot): { label: string; path: string } | null {
  return root ? { label: root.split(/[\\/]/).pop() || root, path: root } : null;
}

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
  const reducedMotion = useSettings((state) => state.settings?.reduceMotion ?? false);
  const promptContext = useMemo(() => createDesktopPromptContext(project.id, root, source.id, sessionId), [sessionId, project.id, root, source.id]);
  const fileActions = useMemo(() => createDesktopFileActions({ sessionId, projectId: project.id, root, sourceId: source.id, promptContext, clipboard: desktopClipboard }), [sessionId, project.id, root, source.id, promptContext]);
  const worktree = useMemo(() => worktreeMark(root), [root]);
  // A file opens with the panel it was opened with — the tree, for one picked there — or with its
  // own default; a tab already showing the file keeps its own unless a panel is asked for.
  const onOpenFile = useCallback((next: string, options?: { target: "current" | "new"; panel?: string }) => {
    const panel = options?.panel;
    void (async () => {
      if (options?.target !== "new") {
        const strip = await readSessionStrip(sessionId);
        if (!strip.tabs.some(tab => tab.kind === "file" && tab.path === next && tab.root === root)) {
          await updateSessionTab(sessionId, tabId, { path: next, panel: panel ?? null });
          return;
        }
      }
      // A new tab, or the one already showing the file.
      await openSessionTab(sessionId, project.id, root, "file", panel === undefined ? { path: next } : { path: next, panel });
    })().catch(error => toast.error(error instanceof Error ? error.message : String(error)));
  }, [sessionId, project.id, tabId, root]);
  const liveDocuments = useMemo(() => desktopLiveDocuments(tabId, { projectId: project.id, root }), [tabId, project.id, root]);
  const host = useMemo<ViewerHost>(() => ({
    ...liveDocuments, files: source, fileActions, clipboard: desktopClipboard, promptContext,
    navigation: { openFile: onOpenFile }, environment: { colorScheme, platform: fileActions.platform, reducedMotion },
  }), [source, fileActions, promptContext, onOpenFile, colorScheme, reducedMotion, liveDocuments]);
  return <FileViewer file={path} host={host} renderers={composition.renderers} state={state} onStateChange={onStateChange}
    reveal={reveal?.root === root ? reveal : null}
    onError={(error) => toast.error(error.message)}
    leading={worktree ? <>
      <TooltipHint content={worktree.path}>
        <span className="flex shrink items-center gap-1 truncate rounded-sm px-0.5 text-muted-foreground" data-crumb="worktree">
          <GitBranch aria-label="Worktree" className="size-3 shrink-0" /><span className="truncate">{worktree.label}</span>
        </span>
      </TooltipHint>
      {path ? <span className="shrink-0 text-muted-foreground/60" aria-hidden>›</span> : null}
    </> : null} />;
}
