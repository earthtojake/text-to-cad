import {
  Check,
  ChevronDown,
  Code2,
  Copy,
  ExternalLink,
  Eye,
  FileText,
  FolderOpen,
  PanelRightOpen,
  RotateCw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@renderer/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import { Spinner } from "@renderer/components/ui/spinner";
import { cn } from "@renderer/lib/utils";
import {
  TREE_MAX_WIDTH,
  TREE_MIN_WIDTH,
  useExplorer,
} from "@renderer/state/explorer";
import type { Project } from "@shared/types";
import type { FileStat, TextFileResult } from "./types";

import { EmptyState } from "./EmptyState";
import { FileTree } from "./FileTree";
import { BinaryRenderer } from "./renderers/BinaryRenderer";
import { CadRenderer } from "./renderers/CadRenderer";
import { CodeRenderer } from "./renderers/CodeRenderer";
import { ImageRenderer } from "./renderers/ImageRenderer";
import { MarkdownRenderer } from "./renderers/MarkdownRenderer";
import { PdfRenderer } from "./renderers/PdfRenderer";
import { rendererFor } from "./renderers/registry";

/**
 * One file, laid out the way Codex lays one out: a header row with the
 * breadcrumb and the actions, the content on the left, and a collapsible file
 * tree on the right.
 *
 * The state machine is small but has one subtlety worth naming. The editor is
 * uncontrolled (see `CodeRenderer`), so "the file on disk changed" cannot be
 * handled by re-rendering with new text — it would fight the person's cursor.
 * Instead the tab notices the change (via `files.changed`) and offers a
 * reload; taking it remounts the editor by bumping `reloadToken`. A tab with
 * no unsaved edits reloads on its own, because there is nothing to lose and a
 * prompt for that is noise.
 */

type Loaded =
  | { state: "empty" }
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "text"; stat: FileStat; file: TextFileResult }
  | { state: "binary"; stat: FileStat; dataUrl: string }
  | { state: "cad"; stat: FileStat }
  | { state: "unsupported"; stat: FileStat };

export function FileTab({
  tabId,
  project,
  path,
  viewSource,
}: {
  tabId: string;
  project: Project;
  path: string | null;
  viewSource: boolean;
}) {
  const update = useExplorer((state) => state.update);
  const openFile = useExplorer((state) => state.openFile);
  const treeCollapsed = useExplorer((state) => state.treeCollapsed);
  const setTreeCollapsed = useExplorer((state) => state.setTreeCollapsed);
  const treeWidth = useExplorer((state) => state.treeWidth);
  const setTreeWidth = useExplorer((state) => state.setTreeWidth);
  const fsRevision = useExplorer((state) => state.fsRevision);
  const treeReveal = useExplorer((state) => state.reveal);

  const [reloadToken, setReloadToken] = useState(0);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  /**
   * What is being shown is `(path, reloadToken)`. Every piece of state that
   * belongs to *that* file carries the key it was produced for, and is read
   * back only when the key still matches.
   *
   * This is the alternative to a pile of reset effects. An effect that clears
   * the draft when the path changes runs *after* a render, so there is one
   * frame in which the new file is on screen with the old file's text in it —
   * and every such effect is another synchronous setState cascading into
   * another render. Deriving during render has neither problem.
   */
  const key = `${path ?? ""}:${reloadToken}`;
  const [result, setResult] = useState<{ key: string; value: Loaded } | null>(null);
  const [draftState, setDraftState] = useState<{ key: string; value: string } | null>(null);
  const [staleKey, setStaleKey] = useState<string | null>(null);

  // Memoised so the two `useCallback`s below do not see a new object on every
  // render: the fallback branches allocate, and `save` depends on it.
  const loaded = useMemo<Loaded>(
    () => (result?.key === key ? result.value : path ? { state: "loading" } : { state: "empty" }),
    [result, key, path],
  );
  const draft = draftState?.key === key ? draftState.value : null;
  const staleOnDisk = staleKey === key;

  const setDraft = useCallback(
    (value: string) => setDraftState({ key, value }),
    [key],
  );

  const dirty = draft !== null && loaded.state === "text" && draft !== loaded.file.content;

  /* ---------------------------------------------------------------------- */
  /* Loading                                                                 */
  /* ---------------------------------------------------------------------- */

  useEffect(() => {
    if (!path) {
      return;
    }
    let cancelled = false;
    const settle = (value: Loaded) => {
      if (!cancelled) {
        setResult({ key, value });
      }
    };

    void (async () => {
      try {
        const stat = await window.hardcore.explorer.stat({ projectId: project.id, path });
        const renderer = rendererFor(stat);
        if (renderer.id === "cad") {
          settle({ state: "cad", stat });
          return;
        }
        if (renderer.id === "image" || renderer.id === "pdf") {
          const binary = await window.hardcore.explorer.readBinary({
            projectId: project.id,
            path,
          });
          settle({ state: "binary", stat, dataUrl: binary.dataUrl });
          return;
        }
        if (renderer.id === "binary") {
          settle({ state: "unsupported", stat });
          return;
        }
        const file = await window.hardcore.explorer.readText({ projectId: project.id, path });
        settle({ state: "text", stat, file });
        if (!cancelled) {
          setDraftState({ key, value: file.content });
        }
      } catch (error) {
        settle({ state: "error", message: messageOf(error) });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [key, path, project.id]);

  /**
   * The watcher fired.
   *
   * A subscription to the store rather than an effect over `fsRevision`,
   * because this is a reaction to an *event*: it has to run when a batch
   * arrives, judged against the draft as it stands at that moment, and not on
   * every render where the condition happens to hold. An untouched tab
   * reloads silently; an edited one is asked, because reloading over unsaved
   * work is the one unrecoverable thing this pane can do.
   */
  // The dirty flag as of the moment the batch arrives, not as of the render
  // that installed the subscription below.
  const dirtyRef = useRef(dirty);
  useEffect(() => {
    dirtyRef.current = dirty;
  }, [dirty]);

  useEffect(() => {
    if (!path) {
      return;
    }
    return useExplorer.subscribe((state, previous) => {
      if (state.fsRevision === previous.fsRevision || !state.changedPaths.includes(path)) {
        return;
      }
      if (dirtyRef.current) {
        setStaleKey(key);
      } else {
        setReloadToken((token) => token + 1);
      }
    });
  }, [key, path]);

  /* ---------------------------------------------------------------------- */
  /* Actions                                                                 */
  /* ---------------------------------------------------------------------- */

  const save = useCallback(async () => {
    if (loaded.state !== "text" || draft === null || saving) {
      return;
    }
    setSaving(true);
    try {
      const written = await window.hardcore.explorer.writeText({
        projectId: project.id,
        path: loaded.stat.path,
        content: draft,
        expectedRevision: loaded.file.revision,
      });
      setResult({ key, value: { state: "text", stat: loaded.stat, file: written } });
      setDraftState({ key, value: written.content });
      setStaleKey(null);
    } catch (error) {
      // The only expected failure is the optimistic lock, and its answer is
      // the same banner the watcher raises: reload, or keep mine.
      setStaleKey(key);
      console.error("[explorer] save failed", error);
    } finally {
      setSaving(false);
    }
  }, [draft, key, loaded, project.id, saving]);

  const copyPath = useCallback(async () => {
    if (!path) {
      return;
    }
    const absolute = await window.hardcore.explorer
      .absolutePath({ projectId: project.id, path })
      .then((result) => result.path)
      .catch(() => path);
    await navigator.clipboard.writeText(absolute).catch(() => {});
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }, [path, project.id]);

  const reveal = useCallback(async () => {
    if (!path) {
      return;
    }
    const absolute = await window.hardcore.explorer
      .absolutePath({ projectId: project.id, path })
      .then((result) => result.path)
      .catch(() => null);
    if (absolute) {
      await window.hardcore.shell.showItemInFolder({ path: absolute }).catch(() => {});
    }
  }, [path, project.id]);

  const openExternally = useCallback(() => {
    if (path) {
      void window.hardcore.explorer.openDefault({ projectId: project.id, path }).catch(() => {});
    }
  }, [path, project.id]);

  /* ---------------------------------------------------------------------- */
  /* The tree's drag handle                                                  */
  /* ---------------------------------------------------------------------- */

  const dragging = useRef(false);
  const onHandleDown = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragging.current = true;
    const surface = event.currentTarget.parentElement;
    const onMove = (move: PointerEvent) => {
      if (!dragging.current || !surface) {
        return;
      }
      // Width is measured from the right edge: the tree is anchored there and
      // the handle drags its left border.
      setTreeWidth(surface.getBoundingClientRect().right - move.clientX);
    };
    const onUp = () => {
      dragging.current = false;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  /* ---------------------------------------------------------------------- */
  /* Render                                                                  */
  /* ---------------------------------------------------------------------- */

  const traits = loaded.state === "text" ? rendererFor(loaded.stat) : null;
  const showingSource = traits?.id !== "markdown" || viewSource;

  const crumbs = useMemo(
    () => [project.name, ...(path ? path.split("/") : [])],
    [project.name, path],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-9 shrink-0 items-center gap-2 border-b px-2">
        <nav
          aria-label="Breadcrumb"
          className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden text-[13px]"
        >
          {crumbs.map((crumb, index) => (
            <span className="flex min-w-0 items-center gap-1" key={`${crumb}-${index}`}>
              {index > 0 ? (
                <span className="shrink-0 text-muted-foreground/60" aria-hidden>
                  ›
                </span>
              ) : null}
              <span
                className={cn(
                  "truncate",
                  index === crumbs.length - 1
                    ? "font-medium text-foreground"
                    : "shrink-0 text-muted-foreground",
                )}
              >
                {crumb}
              </span>
            </span>
          ))}
          {dirty ? (
            <span
              aria-label="Unsaved changes"
              className="ml-1 size-1.5 shrink-0 rounded-full bg-foreground/60"
              title="Unsaved changes"
            />
          ) : null}
        </nav>

        <div className="flex shrink-0 items-center gap-0.5">
          {traits?.sourceToggle ? (
            <Button
              className="h-6 gap-1.5 px-2 text-[12px] text-muted-foreground"
              onClick={() => update(tabId, { viewSource: !viewSource })}
              size="sm"
              variant="ghost"
            >
              {viewSource ? <Eye className="size-3.5" /> : <Code2 className="size-3.5" />}
              {viewSource ? "View preview" : "View source"}
            </Button>
          ) : null}

          <Button
            aria-label="Copy path"
            className="size-6 text-muted-foreground"
            disabled={!path}
            onClick={copyPath}
            size="icon-xs"
            title="Copy path"
            variant="ghost"
          >
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                className="h-6 gap-1 px-2 text-[12px] text-muted-foreground"
                disabled={!path}
                size="sm"
                variant="ghost"
              >
                Open
                <ChevronDown className="size-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuItem onSelect={() => void reveal()}>
                <FolderOpen className="size-3.5" />
                {revealLabel()}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={openExternally}>
                <ExternalLink className="size-3.5" />
                Default application
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {treeCollapsed ? (
            <Button
              aria-label="Show file tree"
              className="size-6 text-muted-foreground"
              onClick={() => setTreeCollapsed(false)}
              size="icon-xs"
              title="Show file tree"
              variant="ghost"
            >
              <PanelRightOpen className="size-3.5" />
            </Button>
          ) : null}
        </div>
      </header>

      {staleOnDisk ? (
        <div className="flex shrink-0 items-center gap-2 border-b bg-amber-500/10 px-3 py-1.5 text-[12px] text-amber-700 dark:text-amber-400">
          <RotateCw className="size-3.5 shrink-0" />
          <span className="flex-1">This file changed on disk since you opened it.</span>
          <Button
            className="h-6 px-2 text-[12px]"
            onClick={() => setReloadToken((token) => token + 1)}
            size="sm"
            variant="secondary"
          >
            Reload
          </Button>
          <Button
            className="h-6 px-2 text-[12px]"
            onClick={() => setStaleKey(null)}
            size="sm"
            variant="ghost"
          >
            Keep mine
          </Button>
        </div>
      ) : null}

      <div className="relative flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-hidden">
          <Body
            draft={draft}
            loaded={loaded}
            onChange={setDraft}
            onOpenExternally={openExternally}
            onOpenFile={(next) => openFile(next)}
            projectId={project.id}
            reloadToken={reloadToken}
            save={save}
            showingSource={showingSource}
          />
        </div>

        {treeCollapsed ? null : (
          <>
            <div
              aria-label="Resize file tree"
              aria-orientation="vertical"
              aria-valuemax={TREE_MAX_WIDTH}
              aria-valuemin={TREE_MIN_WIDTH}
              aria-valuenow={treeWidth}
              className="w-px shrink-0 cursor-col-resize bg-border transition-colors hover:bg-ring data-[dragging=true]:bg-ring"
              onPointerDown={onHandleDown}
              role="separator"
              // A 1px border is the right *look* and a terrible target, so the
              // hit area is widened outward without moving the line.
              style={{ boxShadow: "0 0 0 3px transparent" }}
            />
            <div className="shrink-0 overflow-hidden border-l" style={{ width: treeWidth }}>
              <FileTree
                activePath={path}
                fsRevision={fsRevision}
                // A remount is the reset: a different project is a different
                // tree, with nothing to carry over.
                key={project.id}
                onCollapse={() => setTreeCollapsed(true)}
                onOpen={(next) => openFile(next)}
                projectId={project.id}
                projectName={project.name}
                reveal={treeReveal}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Body({
  loaded,
  draft,
  showingSource,
  reloadToken,
  projectId,
  onChange,
  save,
  onOpenFile,
  onOpenExternally,
}: {
  loaded: Loaded;
  draft: string | null;
  showingSource: boolean;
  reloadToken: number;
  projectId: string;
  onChange: (next: string) => void;
  save: () => void;
  onOpenFile: (path: string) => void;
  onOpenExternally: () => void;
}) {
  switch (loaded.state) {
    case "empty":
      return (
        <EmptyState
          description="Pick one from the tree on the right, or filter by name."
          icon={FileText}
          title="No file open"
        />
      );

    case "loading":
      return (
        <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground">
          <Spinner className="size-3.5" />
          Opening…
        </div>
      );

    case "error":
      return <EmptyState description={loaded.message} icon={FileText} title="Could not open that file" tone="warn" />;

    case "cad":
      return <CadRenderer onOpenFile={onOpenFile} path={loaded.stat.path} projectId={projectId} />;

    case "binary":
      return loaded.stat.fileKind === "pdf" ? (
        <PdfRenderer dataUrl={loaded.dataUrl} name={loaded.stat.name} />
      ) : (
        <ImageRenderer dataUrl={loaded.dataUrl} name={loaded.stat.name} size={loaded.stat.size} />
      );

    case "unsupported":
      return (
        <BinaryRenderer
          extension={loaded.stat.extension}
          name={loaded.stat.name}
          onOpenExternally={onOpenExternally}
          size={loaded.stat.size}
        />
      );

    case "text":
      return showingSource ? (
        <CodeRenderer
          // Remounting on a reload is what replaces the model's text without
          // fighting the cursor — see the note at the top of this file.
          key={`${loaded.stat.path}:${reloadToken}`}
          onChange={onChange}
          onSave={save}
          path={loaded.stat.path}
          readOnly={loaded.file.truncated}
          value={draft ?? loaded.file.content}
        />
      ) : (
        <MarkdownRenderer content={draft ?? loaded.file.content} />
      );
  }
}

function revealLabel(): string {
  return navigator.platform.startsWith("Mac") ? "Reveal in Finder" : "Show in Explorer";
}

function messageOf(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  // Electron wraps a thrown IpcError as "Error invoking remote method '…': …".
  const at = message.lastIndexOf("Error: ");
  return at >= 0 ? message.slice(at + 7) : message;
}
