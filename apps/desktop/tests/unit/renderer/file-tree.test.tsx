import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FileTree } from "@renderer/features/explorer/FileTree";
import { useExplorer } from "@renderer/state/explorer";
import type { DirEntry } from "@shared/ipc/explorer";

/**
 * The tree against a small project listed one level at a time, the way
 * `src/main/explorer/fs.ts` lists one.
 *
 * The bug these cover: expanding a folder more than one level down did
 * nothing. The cause was two sources of truth for "is this folder open" — an
 * override map over a default derived from the open file — so a click on a
 * folder the tree had opened by itself wrote "closed" and issued no listing.
 */

const TREE: Record<string, string[]> = {
  "": ["apps/", "README.md"],
  apps: ["apps/desktop/", "apps/docs/", "apps/viewer/"],
  "apps/desktop": ["apps/desktop/README.md"],
  "apps/viewer": ["apps/viewer/src/", "apps/viewer/README.md"],
  "apps/viewer/src": ["apps/viewer/src/client/", "apps/viewer/src/main.jsx"],
  "apps/viewer/src/client": ["apps/viewer/src/client/CadViewer.js"],
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

function mount(props: Partial<Parameters<typeof FileTree>[0]> = {}) {
  return render(
    <FileTree
      activePath={null}
      fsRevision={0}
      
      onOpen={() => {}}
      projectId="p1"
      projectName="text-to-cad"
      root={null}
      {...props}
    />,
  );
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
    await waitFor(() => expect(rowExists("apps/viewer")).toBe(true));
    await user.click(row("apps/viewer"));
    await waitFor(() => expect(rowExists("apps/viewer/src")).toBe(true));
    await user.click(row("apps/viewer/src"));

    await waitFor(() => expect(rowExists("apps/viewer/src/client")).toBe(true));
    expect(rowExists("apps/viewer/src/main.jsx")).toBe(true);
    // The leaf of the fourth level, to prove the recursion does not stop.
    await user.click(row("apps/viewer/src/client"));
    await waitFor(() => expect(rowExists("apps/viewer/src/client/CadViewer.js")).toBe(true));

    expect(listed).toEqual(["", "apps", "apps/viewer", "apps/viewer/src", "apps/viewer/src/client"]);
  });

  it("expands a folder the tree opened by itself instead of shutting it", async () => {
    const user = userEvent.setup();
    // A file three levels down: `apps`, `apps/viewer` and `apps/viewer/src`
    // are revealed, so they are already open when the tree first draws.
    mount({ activePath: "apps/viewer/src/main.jsx" });

    await waitFor(() => expect(rowExists("apps/viewer/src/client")).toBe(true));
    expect(row("apps")).toHaveAttribute("aria-expanded", "true");

    // A click on an open folder shuts it, and a click on the shut one opens it
    // again with its children — the sequence that used to leave the person
    // clicking folders that never opened.
    await user.click(row("apps/viewer"));
    await waitFor(() => expect(rowExists("apps/viewer/src")).toBe(false));
    await user.click(row("apps/viewer"));
    await waitFor(() => expect(rowExists("apps/viewer/src")).toBe(true));
    expect(rowExists("apps/viewer/src/client")).toBe(true);

    // And a sibling two levels down still opens on one click.
    await user.click(row("apps/desktop"));
    await waitFor(() => expect(rowExists("apps/desktop/README.md")).toBe(true));
  });

  it("reveals a file inside a folder the person had shut", async () => {
    const user = userEvent.setup();
    const view = mount({ activePath: "README.md" });

    await waitFor(() => expect(rowExists("apps")).toBe(true));
    await user.click(row("apps"));
    await waitFor(() => expect(rowExists("apps/viewer")).toBe(true));
    await user.click(row("apps"));
    await waitFor(() => expect(rowExists("apps/viewer")).toBe(false));

    // Opening a file under it has to bring it back, or the tree marks a row
    // as selected inside a subtree it is not showing.
    view.rerender(
      <FileTree
        activePath="apps/viewer/src/main.jsx"
        fsRevision={0}
        
        onOpen={() => {}}
        projectId="p1"
        projectName="text-to-cad"
        root={null}
      />,
    );
    await waitFor(() => expect(rowExists("apps/viewer/src/main.jsx")).toBe(true));
    expect(row("apps/viewer/src/main.jsx")).toHaveAttribute("aria-selected", "true");
  });

  it("keeps what is open when the tab is remounted", async () => {
    const user = userEvent.setup();
    const view = mount();

    await waitFor(() => expect(rowExists("apps")).toBe(true));
    await user.click(row("apps"));
    await waitFor(() => expect(rowExists("apps/viewer")).toBe(true));
    await user.click(row("apps/viewer"));
    await waitFor(() => expect(rowExists("apps/viewer/src")).toBe(true));

    // Opening a file makes a tab, and the pane mounts one tab at a time: this
    // is the remount that used to throw the three levels away. The file is at
    // the root, so nothing here is an ancestor of it — the tree has to be
    // remembering what was open, not re-deriving it from the open file.
    view.unmount();
    mount({ activePath: "README.md" });
    await waitFor(() => expect(rowExists("apps/viewer/src")).toBe(true));
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
      paths: ["apps/viewer/src/main.jsx", "README.md"],
      truncated: false,
    }));
    mount();

    await user.type(screen.getByLabelText("Filter files"), "main");
    await waitFor(() => expect(screen.getByRole("option")).toBeInTheDocument());
    expect(screen.getByRole("option")).toHaveAttribute("title", "apps/viewer/src/main.jsx");
  });
});
