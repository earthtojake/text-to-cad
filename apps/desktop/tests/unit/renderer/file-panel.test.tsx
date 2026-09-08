import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FileTab } from "@renderer/features/explorer/FileTab";
import { useExplorer } from "@renderer/state/explorer";
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
 * The CAD pair is exercised end to end in `tests/e2e/explorer.spec.ts`: the
 * theme editor and the Inspector are the viewer's surface drawn into this
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

/** Replace one `explorer.*` call on the preload bridge, which is read-only. */
function stub(name: keyof typeof window.hardcore.explorer, implementation: unknown) {
  (window.hardcore.explorer as unknown as Record<string, unknown>)[name] = vi.fn(implementation as never);
}

beforeEach(() => {
  window.localStorage.clear();
  useExplorer.setState({
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
  return <FileTab panel={tab.panel} path={tab.path} project={PROJECT} root={tab.root} tabId={tab.id} />;
}

/** A file tab on `AGENTS.md`, with the store's row behind it as the app has. */
async function mount() {
  const tab = useExplorer.getState().open("file", { path: MARKDOWN });
  const view = render(<Host tabId={tab!.id} />);
  await waitFor(() => expect(screen.getByRole("tree")).toBeInTheDocument());
  return { tabId: tab!.id, view };
}

/** The panel column, whichever panel is in it. */
const columns = () => document.querySelectorAll("[data-file-panel-container]");
const openPanelId = () => columns()[0]?.getAttribute("data-file-panel-container") ?? null;
const panelOf = (id: string) => useExplorer.getState().tabs.find((tab) => tab.id === id);

describe("the file tab's panel column", () => {
  it("opens with the tree, and draws exactly one column", async () => {
    await mount();
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
    useExplorer.getState().update(tabId, { panel: "cad-file-sheet" });
    await waitFor(() => expect(columns()).toHaveLength(0));
    // The CAD surface's panels are not this file's, so nothing is open and
    // no toggle is pressed — rather than a column with nothing in it.
    expect(screen.getByRole("button", { name: "Show files" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "View source" })).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps the choice on the tab row, which is what persists it", async () => {
    const { tabId, view } = await mount();
    // Nobody has said yet, so nothing is stamped on the row: the column is
    // showing the renderer's default.
    expect(panelOf(tabId)).toMatchObject({ panel: null });

    await userEvent.click(screen.getByRole("button", { name: "Hide files" }));
    expect(panelOf(tabId)).toMatchObject({ panel: "" });

    // The row is what `explorer_tabs` stores, so this is the whole of
    // persistence: the tab remounted from the same row — another tab
    // selected and this one come back to, or a reload — comes back to the
    // panel the person left, and not to the default.
    view.unmount();
    render(<Host tabId={tabId} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Show files" })).toBeInTheDocument());
    expect(columns()).toHaveLength(0);
  });

  it("gives every panel the one stored width", async () => {
    useExplorer.setState({ panelWidth: 320 });
    await mount();
    expect(columns()[0]).toHaveStyle({ width: "320px" });
    // One handle, named for the panel it sizes, and its value is the width
    // every panel in this column gets.
    const handle = screen.getByRole("separator", { name: "Resize Hide files panel" });
    expect(handle).toHaveAttribute("aria-valuenow", "320");
  });
});
