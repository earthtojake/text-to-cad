import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FileTab } from "@renderer/features/explorer/FileTab";
import { openSessionTab, useExplorer } from "@renderer/state/explorer";
import type { Project } from "@shared/types";

/**
 * The file tab's ONE panel column.
 *
 * The user's rule: a file tab may have one panel open at a time, and the
 * file tree obeys it like every other panel rather than being a second
 * column beside them. So there is one container in the document, one width,
 * one design — and the choice of which panel rides on the tab row, so it
 * survives switching tabs and a reload.
 *
 * A viewer file's panels are exercised end to end in `tests/e2e/explorer.spec.ts`:
 * they are the viewer's surface drawn into this
 * column, and that needs a running `cadgen viewer`. What is testable here is
 * the host's own rule, over markdown's source panel and the tree.
 */
const PROJECT: Project = {
  id: "p1",
  name: "text-to-cad",
  path: "/tmp/text-to-cad",
  createdAt: 0,
};

const MARKDOWN = "AGENTS.md";
const OTHER = "README.md";
/** A root listing with the two documents in it, the way `explorer.list` answers. */
const ROOT_ENTRIES = [MARKDOWN, OTHER].map((path) => ({ path, name: path, kind: "file", size: 12, modifiedAt: 0, symlink: false }));

/** Replace one `explorer.*` call on the preload bridge, which is read-only. */
function stub(name: keyof typeof window.hardcore.explorer, implementation: unknown) {
  (window.hardcore.explorer as unknown as Record<string, unknown>)[name] = vi.fn(implementation as never);
}

beforeEach(() => {
  window.localStorage.clear();
  useExplorer.setState({
    sessionId: "session",
    projectId: PROJECT.id,
    root: null,
    tabs: [],
    activeId: null,
    ready: true,
    trees: {},
    panelWidth: 248,
  });
  stub("stat", async ({ path }: { path: string }) => ({
    path,
    name: path.split("/").pop(),
    kind: "file",
    fileKind: "text",
    extension: path.split(".").pop(),
    size: 12,
    modifiedAt: 0,
    symlink: false,
  }));
  stub("readText", async () => ({ content: "# AGENTS.md\n", revision: "r1", truncated: false }));
  stub("list", async () => []);
  stub("watch", async () => ({}));
  stub("unwatch", async () => ({}));
});

/**
 * The tab, read out of the store the way `ExplorerPane` reads it — so a
 * panel press is a write to the row and the row is what draws the column.
 * That round trip is the thing under test: the choice lives on the tab.
 */
function Host({ tabId }: { tabId: string }) {
  const tab = useExplorer((state) => state.tabs.find((entry) => entry.id === tabId));
  if (!tab || tab.kind !== "file") {
    return null;
  }
  return <FileTab sessionId={tab.sessionId} panel={tab.panel} path={tab.path} project={PROJECT} root={tab.root} tabId={tab.id} />;
}

/** A file tab on `AGENTS.md`, with the store's row behind it as the app has. */
async function mount() {
  const tab = useExplorer.getState().open("file", { path: MARKDOWN });
  const view = render(<Host tabId={tab!.id} />);
  // Registrations load their components lazily: the row's toggles are up once
  // Markdown's document module has been prepared.
  await screen.findByRole("button", { name: "View source" });
  await screen.findByRole("button", { name: "Show files" });
  return { tabId: tab!.id, view };
}

/** The tree, taken up by its toggle: a document does not open on it. */
async function showFiles() {
  await userEvent.click(screen.getByRole("button", { name: "Show files" }));
  await waitFor(() => expect(screen.getByRole("tree")).toBeInTheDocument());
}

/** The panel column, whichever panel is in it. */
const columns = () => document.querySelectorAll("[data-file-panel-container]");
const openPanelId = () => columns()[0]?.getAttribute("data-file-panel-container") ?? null;
const panelOf = (id: string) => useExplorer.getState().tabs.find((tab) => tab.id === id);

describe("the file tab's panel column", () => {
  it("opens with no panel, and draws exactly one column for the one it is given", async () => {
    await mount();
    // A document declares no panel that claims the default, and the tree is
    // not where a file opens — only a tab with no file opens on it.
    expect(columns()).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Show files" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "View source" })).toHaveAttribute("aria-pressed", "false");
    await showFiles();
    expect(columns()).toHaveLength(1);
    expect(openPanelId()).toBe("tree");
    // Named for the accessibility tree by the toggle that opens it.
    expect(screen.getByRole("complementary", { name: "Hide files" })).toBeInTheDocument();
    // One toggle per panel, the tree's last, and the open one is pressed.
    expect([...document.querySelectorAll("[data-file-panel]")].map((el) => el.getAttribute("data-file-panel")))
      .toEqual(["source", "tree"]);
    expect(screen.getByRole("button", { name: "Hide files" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "View source" })).toHaveAttribute("aria-pressed", "false");
  });

  it("closes the open panel when its own toggle is pressed, leaving none", async () => {
    const { tabId } = await mount();
    await showFiles();
    await userEvent.click(screen.getByRole("button", { name: "Hide files" }));
    expect(columns()).toHaveLength(0);
    // `""` is "nothing open" and is not the same as "nobody has said": a tab
    // closed on purpose comes back closed rather than at the default.
    expect(panelOf(tabId)).toMatchObject({ panel: "" });
    expect(screen.getByRole("button", { name: "Show files" })).toHaveAttribute("aria-pressed", "false");
    // ...and the toggle is still in the row, in its place, which is how it
    // comes back. A collapsed panel is not rendered, so nothing else could
    // hold a second copy of the control.
    await userEvent.click(screen.getByRole("button", { name: "Show files" }));
    expect(columns()).toHaveLength(1);
    expect(openPanelId()).toBe("tree");
    expect(panelOf(tabId)).toMatchObject({ panel: "tree" });
  });

  /**
   * Opening another panel closes this one: the field holds ONE id, so it is
   * not possible to write a second panel open, whatever order the writes
   * arrive in. Drawn from the store here rather than by pressing markdown's
   * source toggle, because that panel's body is Monaco and Monaco cannot
   * render in jsdom — `tests/e2e/explorer.spec.ts` presses it for real, and
   * `explorer-helpers.test.ts` has the id table.
   */
  it("draws no column for a panel that is another file's", async () => {
    const { tabId } = await mount();
    await showFiles();
    expect(columns()).toHaveLength(1);
    useExplorer.getState().update(tabId, { panel: "cad-file" });
    await waitFor(() => expect(columns()).toHaveLength(0));
    // A viewer file's panels are not this file's, so nothing is open and
    // no toggle is pressed — rather than a column with nothing in it.
    expect(screen.getByRole("button", { name: "Show files" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "View source" })).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps the choice on the tab row, which is what persists it", async () => {
    const { tabId, view } = await mount();
    // Nobody has said yet, so nothing is stamped on the row: the tab is
    // showing the renderer's default, which for a document is no panel.
    expect(panelOf(tabId)).toMatchObject({ panel: null });

    await showFiles();
    expect(panelOf(tabId)).toMatchObject({ panel: "tree" });

    // The row is what `explorer_tabs` stores, so this is the whole of
    // persistence: the tab remounted from the same row — another tab
    // selected and this one come back to, or a reload — comes back to the
    // panel the person left, and not to the default.
    view.unmount();
    render(<Host tabId={tabId} />);
    await waitFor(() => expect(screen.getByRole("tree")).toBeInTheDocument());
    expect(columns()).toHaveLength(1);
    expect(openPanelId()).toBe("tree");

    // And a tab closed on purpose comes back closed: `""` is not `null`.
    await userEvent.click(screen.getByRole("button", { name: "Hide files" }));
    expect(panelOf(tabId)).toMatchObject({ panel: "" });
  });

  it("gives every panel the one stored width", async () => {
    useExplorer.setState({ panelWidth: 320 });
    await mount();
    await showFiles();
    expect(columns()[0]).toHaveStyle({ width: "320px" });
    // One handle, named for the panel it sizes, and its value is the width
    // every panel in this column gets.
    const handle = screen.getByRole("separator", { name: "Resize Hide files panel" });
    expect(handle).toHaveAttribute("aria-valuenow", "320");
  });
});

/**
 * Which panel a file opens with is said by the way it was reached, and the tab applies it:
 * the viewer asks `openFile(path, { target, panel })` and this app's `FileTab` answers with
 * a tab. A pick in the tree carries the tree, so a person can go on walking it; a crumb
 * carries nothing, so the file opens on its own default.
 */
describe("the panel a file opens with", () => {
  const tabOf = (path: string) => useExplorer.getState().tabs.find((tab) => tab.kind === "file" && tab.path === path);

  it("opens a file picked in the tree in a tab of its own, with the tree open", async () => {
    stub("list", async ({ path }: { path: string }) => (path === "" ? ROOT_ENTRIES : []));
    const { tabId } = await mount();
    await showFiles();
    const row = await waitFor(() => {
      const found = document.querySelector(`[role="treeitem"][data-path="${OTHER}"]`);
      expect(found).not.toBeNull();
      return found as HTMLElement;
    });
    await userEvent.click(row);
    await waitFor(() => expect(tabOf(OTHER)).toMatchObject({ panel: "tree" }));
    expect(tabOf(OTHER)!.id).not.toBe(tabId);
    expect(useExplorer.getState().activeId).toBe(tabOf(OTHER)!.id);
    // The tab it was picked from keeps its own file and its own choice.
    expect(panelOf(tabId)).toMatchObject({ path: MARKDOWN, panel: "tree" });
  });

  it("moves this tab to a file a crumb opens, on that file's own default", async () => {
    stub("list", async ({ path }: { path: string }) => (path === "" ? ROOT_ENTRIES : []));
    const { tabId } = await mount();
    await showFiles();
    expect(panelOf(tabId)).toMatchObject({ panel: "tree" });
    await userEvent.click(screen.getByRole("button", { name: `Browse ${MARKDOWN}` }));
    await userEvent.click(await screen.findByRole("menuitem", { name: OTHER }));
    // The same tab, the other file, and not the tree the last file had open: `null`, the default.
    await waitFor(() => expect(panelOf(tabId)).toMatchObject({ path: OTHER, panel: null }));
    expect(useExplorer.getState().tabs.filter((tab) => tab.kind === "file")).toHaveLength(1);
  });

  it("gives a tab already showing the file the panel it is opened with, and leaves it be when none is asked for", async () => {
    const { tabId } = await mount();
    expect(panelOf(tabId)).toMatchObject({ panel: null });
    await openSessionTab("session", PROJECT.id, null, "file", { path: MARKDOWN, panel: "tree" });
    expect(panelOf(tabId)).toMatchObject({ panel: "tree" });
    expect(useExplorer.getState().tabs.filter((tab) => tab.kind === "file" && tab.path === MARKDOWN)).toHaveLength(1);
    await openSessionTab("session", PROJECT.id, null, "file", { path: MARKDOWN });
    expect(panelOf(tabId)).toMatchObject({ panel: "tree" });
    await waitFor(() => expect(columns()).toHaveLength(1));
    expect(openPanelId()).toBe("tree");
  });

  it("fills the blank tab with the file and the panel it is opened with, or the file's default", async () => {
    const blank = useExplorer.getState().open("file")!;
    await openSessionTab("session", PROJECT.id, null, "file", { path: OTHER, panel: "tree" });
    expect(panelOf(blank.id)).toMatchObject({ path: OTHER, panel: "tree" });
    const second = useExplorer.getState().open("file")!;
    await openSessionTab("session", PROJECT.id, null, "file", { path: MARKDOWN });
    expect(panelOf(second.id)).toMatchObject({ path: MARKDOWN, panel: null });
  });
});
