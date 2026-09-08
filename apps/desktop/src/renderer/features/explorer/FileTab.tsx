import { FileText, GitBranch, RotateCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@renderer/components/ui/button";
import { Spinner } from "@renderer/components/ui/spinner";
import { useElementWidth } from "@renderer/hooks/use-element-width";
import { useExplorer } from "@renderer/state/explorer";
import { FILE_PANEL_TREE, type ExplorerRoot, type Project } from "@shared/types";
import type { FileStat, TextFileResult } from "./types";

import { buildCrumbs, worktreeMark } from "./crumbs";
import { Breadcrumbs } from "./Breadcrumbs";
import { EmptyState } from "./EmptyState";
import { currentPlatform, type EntryActionContext } from "./entry-actions";
import { FilePanel } from "./FilePanel";
import { FileTree, type TreeEdit, type TreeEditRequest } from "./FileTree";
import { BinaryRenderer } from "./renderers/BinaryRenderer";
import { CadRenderer } from "./renderers/CadRenderer";
import { CodeRenderer } from "./renderers/CodeRenderer";
import { ImageRenderer } from "./renderers/ImageRenderer";
import { MarkdownRenderer } from "./renderers/MarkdownRenderer";
import {
  CAD_PANEL,
  nextOpenPanel,
  panelsFor,
  resolveOpenPanel,
  SOURCE_PANEL,
} from "./renderers/panels";
import { PdfRenderer } from "./renderers/PdfRenderer";
import { rendererFor } from "./renderers/registry";

/**
 * One file, laid out the way Codex lays one out: a header row with the
 * breadcrumb and the actions, the content on the left, and ONE panel column
 * on the right — the file tree, or the CAD surface's theme editor, or its
 * Inspector, or markdown's source over the content itself. Exactly one of
 * them, or none (`renderers/panels.ts`, `FilePanel.tsx`).
 *
 * The state machine is small but has one subtlety worth naming. The editor is
 * uncontrolled (see `CodeRenderer`), so "the file on disk changed" cannot be
 * handled by re-rendering with new text — it would fight the person's cursor.
 * Instead the tab notices the change (via `files.changed`) and offers a
 * reload; taking it remounts the editor by bumping `reloadToken`. A tab with
 * no unsaved edits reloads on its own, because there is nothing to lose and a
 * prompt for that is noise.
 */

/**
 * One class for every toggle at the end of the nav row — the renderer's
 * panels and the files toggle — so "highlighted while its panel is open"
 * looks the same on all of them, and the same as the standalone viewer's
 * top-bar toggles (`activeIconButtonClasses` there).
 */
const PANEL_TOGGLE_CLASSES =
  "size-6 text-muted-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground";

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
  root,
  path,
  panel,
}: {
  tabId: string;
  project: Project;
  /** The directory `path` is relative to: null for the project, else a worktree (plan §9). */
  root: ExplorerRoot;
  path: string | null;
  /** Which panel this tab has open, by id; null is the renderer's default. */
  panel: string | null;
}) {
  const update = useExplorer((state) => state.update);
  const openFile = useExplorer((state) => state.openFile);
  const panelWidth = useExplorer((state) => state.panelWidth);
  const setPanelWidth = useExplorer((state) => state.setPanelWidth);
  const fsRevision = useExplorer((state) => state.fsRevision);
  const treeReveal = useExplorer((state) => state.reveal);

  const [reloadToken, setReloadToken] = useState(0);
  const [saving, setSaving] = useState(false);
  const [rootRef, paneWidth] = useElementWidth();
  // Every read and write of this file names its root as well as its project.
  const at = useMemo(() => ({ projectId: project.id, ...(root ? { root } : {}) }), [project.id, root]);

  /**
   * A tab whose root is not the strip's — a worktree file kept open after
   * the person switched to a thread in the checkout — watches its own root
   * for as long as it is on screen, so an edit by that thread's agent still
   * reaches it. Refcounted in main; the strip's own watch is separate.
   */
  const activeRoot = useExplorer((state) => state.root);
  useEffect(() => {
    if (root === activeRoot) {
      return;
    }
    void window.hardcore.explorer.watch(at).catch(() => {});
    return () => {
      void window.hardcore.explorer.unwatch(at).catch(() => {});
    };
  }, [at, root, activeRoot]);

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
        const stat = await window.hardcore.explorer.stat({ ...at, path });
        const renderer = rendererFor(stat);
        if (renderer.id === "cad") {
          settle({ state: "cad", stat });
          return;
        }
        if (renderer.id === "image" || renderer.id === "pdf") {
          const binary = await window.hardcore.explorer.readBinary({ ...at, path });
          settle({ state: "binary", stat, dataUrl: binary.dataUrl });
          return;
        }
        if (renderer.id === "binary") {
          settle({ state: "unsupported", stat });
          return;
        }
        const file = await window.hardcore.explorer.readText({ ...at, path });
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
  }, [key, path, at]);

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
      if (
        state.fsRevision === previous.fsRevision ||
        state.changedRoot !== root ||
        !state.changedPaths.includes(path)
      ) {
        return;
      }
      if (dirtyRef.current) {
        setStaleKey(key);
      } else {
        setReloadToken((token) => token + 1);
      }
    });
  }, [key, path, root]);

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
        ...at,
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
  }, [draft, key, loaded, at, saving]);

  const openExternally = useCallback(() => {
    if (path) {
      void window.hardcore.explorer.openDefault({ ...at, path }).catch(() => {});
    }
  }, [path, at]);

  /* ---------------------------------------------------------------------- */
  /* Render                                                                  */
  /* ---------------------------------------------------------------------- */

  const traits = "stat" in loaded ? rendererFor(loaded.stat) : null;

  /**
   * The tab's panels, and which one is open (`renderers/panels.ts`).
   *
   * One open panel, held as one id in one persisted field of the tab, so the
   * toggles cannot disagree with the column and a reload comes back to the
   * panel the person left up. `null` — nobody has said — resolves to the
   * renderer's own default: the Inspector for a CAD file, the tree for
   * everything else.
   *
   * `ready` says the body is the renderer's own surface: a CAD tab whose
   * runtime did not start shows a failure card, and the CAD declaration
   * answers with no panels at all rather than two dead controls.
   */
  const [readyFor, setReadyFor] = useState<string | null>(null);
  const onSurfaceReady = useCallback(
    (ready: boolean) => setReadyFor((current) => (ready ? key : current === key ? null : current)),
    [key],
  );
  const openId = useMemo(() => {
    const declared = traits?.panels?.({ open: panel ?? "", ready: readyFor === key }) ?? [];
    return resolveOpenPanel(panelsFor(declared, panel ?? ""), panel)?.id ?? "";
  }, [key, panel, readyFor, traits]);
  // Named a second time with the open id settled, so a declaration reading
  // `open` — markdown's source toggle, which is `View source` or `View
  // preview` — is drawn with the answer rather than with the raw field.
  const panels = panelsFor(traits?.panels?.({ open: openId, ready: readyFor === key }) ?? [], openId);
  const openPanel = panels.find((entry) => entry.id === openId) ?? null;
  const setPanel = useCallback(
    (next: string) => update(tabId, { panel: next }),
    [tabId, update],
  );
  const showingSource = traits?.id !== "markdown" || openId === SOURCE_PANEL;
  /**
   * The box the file's renderer draws its own panel into — the CAD surface
   * portals its theme editor and its Inspector there (`panelSlot`). State
   * rather than a ref, because the renderer has to be told when it attaches.
   */
  const [panelSlot, setPanelSlot] = useState<HTMLDivElement | null>(null);
  /** How much of the pane the panel column is taking: zero when none is drawn. */
  const panelColumnWidth = openPanel && openPanel.content !== "body" ? panelWidth : 0;

  /**
   * The breadcrumb's entry menus. `Rename` on the file crumb is the one
   * item drawn here — a field over the crumb — and `New …` from a folder
   * crumb, or a rename of one, goes to the tree, which is where a row can
   * be typed into; the tree is shown for it if it was hidden.
   */
  const [renamingCrumb, setRenamingCrumb] = useState(false);
  const [treeEdit, setTreeEdit] = useState<TreeEdit | null>(null);

  /**
   * A file picked from a crumb's menu opens *here*: the breadcrumb is this
   * tab's address bar, and a sibling chosen from it is where this tab goes
   * next — the tree's rows open tabs, this does not. A file already open
   * elsewhere in the strip is brought forward instead of shown twice.
   */
  const openHere = useCallback(
    (next: string) => {
      const { tabs, setActive } = useExplorer.getState();
      const existing = tabs.find((tab) => tab.kind === "file" && tab.path === next && tab.root === root);
      if (existing && existing.id !== tabId) {
        setActive(existing.id);
        return;
      }
      // A different file is a different renderer with different panels, so
      // the choice does not carry: `null` opens the new file the way opening
      // it in a fresh tab would.
      update(tabId, { path: next, panel: null });
    },
    [tabId, root, update],
  );
  const crumbCtx = useMemo<EntryActionContext>(() => {
    // The tree is where a row can be typed into, so an edit asked for from a
    // crumb opens it — over whatever panel was up, because one is open at a
    // time.
    const askTree = (edit: TreeEditRequest) => {
      update(tabId, { panel: FILE_PANEL_TREE });
      setTreeEdit((previous) => ({ ...edit, nonce: (previous?.nonce ?? 0) + 1 }));
    };
    return {
      projectId: project.id,
      root,
      platform: currentPlatform(),
      beginRename: (entry) => {
        if (entry.path === path) {
          setRenamingCrumb(true);
        } else {
          askTree({ mode: "rename", entry });
        }
      },
      beginCreate: (directory, kind) => askTree({ mode: "create", directory, kind }),
    };
  }, [project.id, root, path, tabId, update]);

  /**
   * The breadcrumb: the path's segments below the root, each a menu of its
   * neighbours (`crumbs.ts` for the rule, `Breadcrumbs.tsx` for the drawing).
   * There is no crumb for the project or the worktree — a root's neighbours
   * are outside the project, which this pane may not list. In a pane too
   * narrow for the folders they fold into one `…` (Codex does the same)
   * rather than each truncating to two letters; the full path is the tooltip
   * either way.
   */
  const crumbs = useMemo(
    () =>
      buildCrumbs({
        path,
        narrow: paneWidth > 0 && paneWidth - panelColumnWidth < 720,
      }),
    [path, paneWidth, panelColumnWidth],
  );
  const worktree = useMemo(() => worktreeMark(root), [root]);

  return (
    <div className="flex h-full min-h-0 flex-col" ref={rootRef}>
      <header className="flex h-9 shrink-0 items-center gap-2 border-b px-2">
        {/*
          The file's name is the crumb that matters, so it is the one that
          never shrinks; the project and the folders give up their width
          first and truncate. Every crumb is `min-w-0` so flex can take the
          width back — a `shrink-0` on the folders is how they were drawn
          over each other in a narrow pane.
        */}
        <nav
          aria-label="Breadcrumb"
          className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden text-[13px]"
        >
          {/*
            The worktree this file is in, when it is in one — a label, not a
            crumb (`worktreeMark` in `crumbs.ts` for why it has no menu).
          */}
          {worktree ? (
            <>
              <span
                className="flex shrink items-center gap-1 truncate rounded-sm px-0.5 text-muted-foreground"
                data-crumb="worktree"
                title={worktree.title}
              >
                <GitBranch aria-label="Worktree" className="size-3 shrink-0" />
                <span className="truncate">{worktree.label}</span>
              </span>
              {crumbs.length > 0 ? (
                <span className="shrink-0 text-muted-foreground/60" aria-hidden>
                  ›
                </span>
              ) : null}
            </>
          ) : null}
          <Breadcrumbs
            activePath={path}
            crumbs={crumbs}
            ctx={crumbCtx}
            onOpen={openHere}
            onRenamed={() => setRenamingCrumb(false)}
            onRenameEnd={() => setRenamingCrumb(false)}
            renaming={renamingCrumb && path !== null}
          />
          {dirty ? (
            <span
              aria-label="Unsaved changes"
              className="ml-1 size-1.5 shrink-0 rounded-full bg-foreground/60"
              title="Unsaved changes"
            />
          ) : null}
        </nav>

        {/*
          The actions that used to be here — Copy path, Open ▾ — live in the
          entry menus now (right-click a crumb or a row). What is left is one
          toggle per panel this file has, in declaration order with the files
          toggle last, and never any other order: the right end of this row
          is the same control whatever is open and whatever kind of file this
          is, so it is the one thing in the pane a person can always find in
          the same place.
        */}
        <div className="flex shrink-0 items-center gap-0.5">
          {panels.map((entry) => (
            <Button
              aria-label={entry.label}
              aria-pressed={entry.id === openId}
              className={PANEL_TOGGLE_CLASSES}
              data-file-panel={entry.id}
              {...(entry.id === FILE_PANEL_TREE ? { "data-testid": "tree-toggle" } : {})}
              key={entry.id}
              onClick={() => setPanel(nextOpenPanel(openId, entry.id))}
              size="icon-xs"
              title={entry.label}
              variant="ghost"
            >
              <entry.icon className="size-3.5" />
            </Button>
          ))}
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
            onOpenFile={(next) => openFile(next, root)}
            onPanelOpen={setPanel}
            onSurfaceReady={onSurfaceReady}
            openPanel={openId}
            panelSlot={panelSlot}
            projectId={project.id}
            reloadToken={reloadToken}
            root={root}
            tabId={tabId}
            save={save}
            showingSource={showingSource}
          />
        </div>

        {/*
          The one panel column, whatever is in it (`FilePanel.tsx`). A panel
          whose content IS the body — markdown's source — draws no column;
          everything else gets this frame, and the file's renderer that draws
          its own panel gets the box to draw into.
        */}
        {openPanel && openPanel.content !== "body" ? (
          <FilePanel
            id={openPanel.id}
            label={openPanel.label}
            onWidthChange={setPanelWidth}
            width={panelWidth}
          >
            {openPanel.content === "tree" ? (
              <FileTree
                activePath={path}
                edit={treeEdit}
                fsRevision={fsRevision}
                // A different project or root is a different tree. The
                // state is the store's, per root; the key keeps the filter
                // and the cursor from crossing over with it.
                key={`${project.id}:${root ?? ""}`}
                onOpen={(next) => openFile(next, root)}
                projectId={project.id}
                projectName={project.name}
                reveal={treeReveal}
                root={root}
              />
            ) : (
              <div className="h-full min-h-0" ref={setPanelSlot} />
            )}
          </FilePanel>
        ) : null}
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
  root,
  tabId,
  openPanel,
  panelSlot,
  onChange,
  save,
  onOpenFile,
  onOpenExternally,
  onPanelOpen,
  onSurfaceReady,
}: {
  loaded: Loaded;
  draft: string | null;
  showingSource: boolean;
  reloadToken: number;
  projectId: string;
  root: ExplorerRoot;
  tabId: string;
  /** The id of the tab's open panel; a renderer with panels reads its own. */
  openPanel: string;
  /** The panel column's box, when the open panel is one the renderer draws. */
  panelSlot: HTMLElement | null;
  onChange: (next: string) => void;
  save: () => void;
  onOpenFile: (path: string) => void;
  onOpenExternally: () => void;
  /** Open a panel by id, or `""` for none — what the toggles do. */
  onPanelOpen: (id: string) => void;
  onSurfaceReady: (ready: boolean) => void;
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
      return (
        <CadRenderer
          /*
            The surface's two panels are this tab's, driven as controlled
            props: one id is open here, so at most one of these is true and
            the surface never has a flag of its own to disagree with
            (`apps/viewer/docs/file-view.md`).
          */
          fileSheetOpen={openPanel === CAD_PANEL.fileSheet}
          // What the surface does on its own — the sheet opening because a
          // measurement landed — comes back through here and becomes the
          // tab's open panel, closing whatever else was up. So the highlight
          // follows the screen rather than the last press.
          onFileSheetOpenChange={(next) => onPanelOpen(closedBy(next, openPanel, CAD_PANEL.fileSheet))}
          onOpenFile={onOpenFile}
          onSurfaceReady={onSurfaceReady}
          onThemeEditingChange={(next) => onPanelOpen(closedBy(next, openPanel, CAD_PANEL.theme))}
          panelSlot={panelSlot}
          path={loaded.stat.path}
          projectId={projectId}
          root={root}
          tabId={tabId}
          themeEditing={openPanel === CAD_PANEL.theme}
        />
      );

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
        <MarkdownRenderer
          content={draft ?? loaded.file.content}
          editable={!loaded.file.truncated}
          // The same remount-on-reload as Monaco, for the same reason: a
          // live document cannot take new text without moving the cursor.
          key={`${loaded.stat.path}:${reloadToken}`}
          onChange={onChange}
          onSave={save}
        />
      );
  }
}

/**
 * What the tab's panel becomes when the surface reports one of its own open
 * or shut.
 *
 * `true` opens it, over whatever was up. `false` is only ever about the
 * panel it names: the surface reports both of its flags on every change, so
 * a "the sheet is shut" arriving while the file TREE is the open panel must
 * leave the tree alone rather than close the column.
 */
function closedBy(open: boolean, current: string, id: string): string {
  if (open) {
    return id;
  }
  return current === id ? "" : current;
}

function messageOf(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  // Electron wraps a thrown IpcError as "Error invoking remote method '…': …".
  const at = message.lastIndexOf("Error: ");
  return at >= 0 ? message.slice(at + 7) : message;
}
