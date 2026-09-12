import { FileViewer, defineFileRenderer } from "@hardcore/ui/file-viewer";
import { useMemo } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createDesktopFileSource } from "@renderer/features/explorer/adapters/fileSource";
import { useExplorer, useTree } from "@renderer/state/explorer";
import type { DirEntry } from "@shared/ipc/explorer";

/**
 * The SHARED tree (`@hardcore/ui/navigation`) over THIS app's source adapter
 * (`features/explorer/adapters/fileSource.ts`), against a small project listed one
 * level at a time, the way `src/main/explorer/fs.ts` lists one.
 *
 * The component is the standalone CAD Viewer's too, and its pure halves are
 * tested beside it (`packages/ui/src/file-viewer/navigation/*.test.js`). What is under
 * test here is the half that needs a DOM and an IPC bridge: that this app's
 * adapter reads the directories the tree asks for, and that the rows, the
 * menus and the keyboard behave over it.
 *
 * The bug these cover: expanding a folder more than one level down did
 * nothing. The cause was two sources of truth for "is this folder open" — an
 * override map over a default derived from the open file — so a click on a
 * folder the tree had opened by itself wrote "closed" and issued no listing.
 */

const TREE: Record<string, string[]> = {
  "": ["apps/", "README.md"],
  apps: ["apps/desktop/", "apps/docs/", "apps/web/"],
  "apps/desktop": ["apps/desktop/README.md"],
  "apps/web": ["apps/web/src/", "apps/web/README.md"],
  "apps/web/src": ["apps/web/src/client/", "apps/web/src/main.jsx"],
  "apps/web/src/client": ["apps/web/src/client/CadViewer.js"],
  "apps/docs": ["apps/docs/index.md"],
};

function entriesOf(directory: string): DirEntry[] {
  return (TREE[directory] ?? []).map((raw) => {
    const isDirectory = raw.endsWith("/");
    const path = isDirectory ? raw.slice(0, -1) : raw;
    return {
      path,
      name: path.split("/").pop() ?? path,
      kind: isDirectory ? ("directory" as const) : ("file" as const),
      size: 0,
      modifiedAt: 0,
      symlink: false,
    };
  });
}

let listed: string[];

/** Replace one `explorer.*` call on the preload bridge, which is read-only. */
function stub(name: keyof typeof window.hardcore.explorer, implementation: unknown) {
  (window.hardcore.explorer as unknown as Record<string, unknown>)[name] = vi.fn(implementation as never);
}

beforeEach(() => {
  listed = [];
  useExplorer.setState({ trees: {} });
  stub("list", async ({ path }: { path: string }) => {
    listed.push(path);
    return entriesOf(path);
  });
});

/**
 * The tree as the file tab draws it: the shared component over this app's
 * adapter. A component rather than a call, because the adapter is a hook.
 */
const testRenderers = [defineFileRenderer({
  id: "test", priority: 0, matches: () => true,
  prepare: async () => ({ data: null }), load: async () => ({ default: () => null }),
})];
function Tree({ activePath = null }: { activePath?: string | null }) {
  const source = useMemo(() => createDesktopFileSource({ projectId: "p1", root: null, projectName: "text-to-cad" }), []);
  const { open } = useTree(null);
  return <FileViewer file={activePath} source={source} renderers={testRenderers}
    state={{ panel: "tree", panelWidth: 300, expandedDirectories: [...open] }}
    onStateChange={(next) => useExplorer.getState().setTreeOpen(null, () => new Set(next.expandedDirectories))}
    onOpenFile={() => {}} />;
}

function mount(props: { activePath?: string | null } = {}) {
  return render(<Tree {...props} />);
}

/** A row by its path, which is what a nested folder is keyed by. */
const row = (path: string) => document.querySelector(`[data-path="${path}"]`) as HTMLElement;
const rowExists = (path: string) => document.querySelector(`[data-path="${path}"]`) !== null;

describe("FileTree", () => {
  it("expands three levels of subfolders, one listing each", async () => {
    const user = userEvent.setup();
    mount();

    await waitFor(() => expect(rowExists("apps")).toBe(true));
    await user.click(row("apps"));
    await waitFor(() => expect(rowExists("apps/web")).toBe(true));
    await user.click(row("apps/web"));
    await waitFor(() => expect(rowExists("apps/web/src")).toBe(true));
    await user.click(row("apps/web/src"));

    await waitFor(() => expect(rowExists("apps/web/src/client")).toBe(true));
    expect(rowExists("apps/web/src/main.jsx")).toBe(true);
    // The leaf of the fourth level, to prove the recursion does not stop.
    await user.click(row("apps/web/src/client"));
    await waitFor(() => expect(rowExists("apps/web/src/client/CadViewer.js")).toBe(true));

    expect(listed).toEqual(["", "apps", "apps/web", "apps/web/src", "apps/web/src/client"]);
  });

  it("expands a folder the tree opened by itself instead of shutting it", async () => {
    const user = userEvent.setup();
    // A file three levels down: `apps`, `apps/web` and `apps/web/src`
    // are revealed, so they are already open when the tree first draws.
    mount({ activePath: "apps/web/src/main.jsx" });

    await waitFor(() => expect(rowExists("apps/web/src/client")).toBe(true));
    expect(row("apps")).toHaveAttribute("aria-expanded", "true");

    // A click on an open folder shuts it, and a click on the shut one opens it
    // again with its children — the sequence that used to leave the person
    // clicking folders that never opened.
    await user.click(row("apps/web"));
    await waitFor(() => expect(rowExists("apps/web/src")).toBe(false));
    await user.click(row("apps/web"));
    await waitFor(() => expect(rowExists("apps/web/src")).toBe(true));
    expect(rowExists("apps/web/src/client")).toBe(true);

    // And a sibling two levels down still opens on one click.
    await user.click(row("apps/desktop"));
    await waitFor(() => expect(rowExists("apps/desktop/README.md")).toBe(true));
  });

  it("reveals a file inside a folder the person had shut", async () => {
    const user = userEvent.setup();
    const view = mount({ activePath: "README.md" });

    await waitFor(() => expect(rowExists("apps")).toBe(true));
    await user.click(row("apps"));
    await waitFor(() => expect(rowExists("apps/web")).toBe(true));
    await user.click(row("apps"));
    await waitFor(() => expect(rowExists("apps/web")).toBe(false));

    // Opening a file under it has to bring it back, or the tree marks a row
    // as selected inside a subtree it is not showing.
    view.rerender(<Tree activePath="apps/web/src/main.jsx" />);
    await waitFor(() => expect(rowExists("apps/web/src/main.jsx")).toBe(true));
    expect(row("apps/web/src/main.jsx")).toHaveAttribute("aria-selected", "true");
  });

  it("keeps what is open when the tab is remounted", async () => {
    const user = userEvent.setup();
    const view = mount();

    await waitFor(() => expect(rowExists("apps")).toBe(true));
    await user.click(row("apps"));
    await waitFor(() => expect(rowExists("apps/web")).toBe(true));
    await user.click(row("apps/web"));
    await waitFor(() => expect(rowExists("apps/web/src")).toBe(true));

    // Opening a file makes a tab, and the pane mounts one tab at a time: this
    // is the remount that used to throw the three levels away. The file is at
    // the root, so nothing here is an ancestor of it — the tree has to be
    // remembering what was open, not re-deriving it from the open file.
    view.unmount();
    mount({ activePath: "README.md" });
    await waitFor(() => expect(rowExists("apps/web/src")).toBe(true));
  });

  it("aims one context menu at the row that was clicked, and at the root elsewhere", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(rowExists("README.md")).toBe(true));

    // A file's menu on a file row…
    await user.pointer({ keys: "[MouseRight]", target: row("README.md") });
    await waitFor(() => expect(screen.getByRole("menu")).toBeInTheDocument());
    expect(screen.getByRole("menu")).toHaveAttribute("data-entry-menu", "README.md");
    expect(screen.getByRole("menuitem", { name: /Duplicate/ })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /New folder/ })).toBeNull();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());

    // …and the root's on the space under the rows.
    await user.pointer({ keys: "[MouseRight]", target: screen.getByRole("tree") });
    await waitFor(() => expect(screen.getByRole("menu")).toBeInTheDocument());
    expect(screen.getByRole("menu")).toHaveAttribute("data-entry-menu", "");
    expect(screen.getByRole("menuitem", { name: /New folder/ })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Move to Trash/ })).toBeNull();
    await user.keyboard("{Escape}");
  });

  it("renames the cursor row on F2 and puts the name back on Escape", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(rowExists("README.md")).toBe(true));

    await user.click(row("README.md"));
    screen.getByRole("tree").focus();
    await user.keyboard("{F2}");
    const field = await screen.findByLabelText("Rename README.md");
    expect(field).toHaveFocus();
    // The stem is selected, not the extension.
    expect((field as HTMLInputElement).selectionStart).toBe(0);
    expect((field as HTMLInputElement).selectionEnd).toBe("README".length);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByLabelText("Rename README.md")).toBeNull());
    expect(window.hardcore.explorer.rename).not.toHaveBeenCalled();

    // Enter commits through main, and the row follows the answer.
    await user.keyboard("{F2}");
    await user.keyboard("{Control>}a{/Control}NOTES.md{Enter}");
    await waitFor(() => expect(window.hardcore.explorer.rename).toHaveBeenCalledWith({ projectId: "p1", path: "README.md", name: "NOTES.md" }));
  });

  it("filters to a flat list of paths", async () => {
    const user = userEvent.setup();
    stub("paths", async () => ({
      paths: ["apps/web/src/main.jsx", "README.md"],
      truncated: false,
    }));
    mount();

    await user.type(screen.getByLabelText("Filter files"), "main");
    await waitFor(() => expect(screen.getByRole("option")).toBeInTheDocument());
    expect(screen.getByRole("option")).toHaveAttribute("title", "apps/web/src/main.jsx");
  });
});
