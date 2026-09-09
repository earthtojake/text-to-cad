import { FileViewer } from "@hardcore/ui/file-viewer";
import { EmptyState, worktreeMark } from "@hardcore/ui/navigation";
import { FileText, GitBranch } from "lucide-react";
import { useCallback, useEffect, useMemo } from "react";
import { toast } from "sonner";
import { useResolvedTheme } from "@renderer/hooks/use-theme";
import { useExplorer } from "@renderer/state/explorer";
import { useProjects } from "@renderer/state/projects";
import type { ExplorerRoot, Project } from "@shared/types";
import { createDesktopFileSource } from "./adapters/fileSource";
import { useDesktopViewState } from "./adapters/persistence";
import { createDesktopRenderers } from "./renderers";
import { AddFilesButton } from "./AddFilesButton";

/** The desktop supplies a root, native services and tab navigation to the shared viewer. */
export function FileTab({ tabId, project, root, path, panel }: {
  tabId: string; project: Project; root: ExplorerRoot; path: string | null; panel: string | null;
}) {
  const source = useMemo(() => createDesktopFileSource({ projectId: project.id,
    projectName: () => useProjects.getState().projects.find(entry => entry.id === project.id)?.name ?? "Project", root }), [project.id, root]);
  const composition = useMemo(() => createDesktopRenderers(project.id, root, tabId), [project.id, root, tabId]);
  useEffect(() => () => composition.dispose(), [composition]);
  const { state, onStateChange } = useDesktopViewState(source.id, tabId, root, panel, root ?? project.path);
  const reveal = useExplorer((state) => state.reveal);
  const colorScheme = useResolvedTheme();
  const worktree = useMemo(() => worktreeMark(root), [root]);
  const onOpenFile = useCallback((next: string, options?: { target: "current" | "new" }) => {
    const explorer = useExplorer.getState();
    if (options?.target === "new") { explorer.openFile(next, root); return; }
    const existing = explorer.tabs.find((tab) => tab.kind === "file" && tab.path === next && tab.root === root);
    if (existing) { if (existing.id !== tabId) explorer.setActive(existing.id); return; }
    explorer.update(tabId, { path: next, panel: null });
  }, [tabId, root]);
  return <FileViewer file={path} source={source} renderers={composition.renderers} state={state} onStateChange={onStateChange}
    onOpenFile={onOpenFile} appearance={{ colorScheme }} reveal={reveal?.root === root ? reveal : null}
    presentation={{ treeActions: <AddFilesButton projectId={project.id} root={root} />, empty: <EmptyState icon={FileText} title="Open a file"
      description="Choose a project file, or add files from your computer — STEP, images, PDFs, code and more."
      action={<AddFilesButton projectId={project.id} root={root} />} /> }}
    onError={(error) => toast.error(error.message)}
    leading={worktree ? <>
      <span className="flex shrink items-center gap-1 truncate rounded-sm px-0.5 text-muted-foreground" data-crumb="worktree" title={worktree.title}>
        <GitBranch aria-label="Worktree" className="size-3 shrink-0" /><span className="truncate">{worktree.label}</span>
      </span>
      {path ? <span className="shrink-0 text-muted-foreground/60" aria-hidden>›</span> : null}
    </> : null} />;
}
