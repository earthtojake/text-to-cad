/**
 * The file tab's breadcrumb, as data.
 *
 * The crumbs are the path segments BELOW the explorer's root, and nothing
 * else: `STL/link_plate.stl` is `STL › link_plate.stl`, with no crumb for the
 * project or the worktree it sits in.
 *
 * Each crumb's menu is its NEIGHBOURS — the listing of its PARENT directory,
 * with the crumb's own entry marked. So the first crumb lists the root, a
 * folder crumb lists what sits beside that folder, and the file crumb lists
 * its siblings; the menus read as "what else is here, at this level" from
 * left to right, and a crumb never lists anything above the root. That is
 * why there is no root crumb: the root's neighbours are outside the project,
 * which is not a thing this pane may show. A file at the root is one crumb,
 * listing the root.
 *
 * Picking a file opens it; picking a folder opens a submenu of that folder,
 * the way the CAD Viewer's own breadcrumb does
 * (`apps/viewer/src/client/workbench/breadcrumbs.js`, re-thought here for a
 * tree that is listed one directory at a time).
 *
 * Pure: the component reads listings from the explorer store and draws
 * what this returns, and the unit test reads it directly.
 */
import type { DirEntry } from "@shared/ipc/explorer";
import type { ExplorerRoot } from "@shared/types";

export type CrumbKind = "directory" | "file" | "ellipsis";

export type Crumb = {
  kind: CrumbKind;
  label: string;
  /** The tooltip: the full segment, or the folded folders joined. */
  title: string;
  /** Root-relative path of what the crumb names; never `""`. */
  path: string;
  /**
   * The directory whose listing the crumb's menu shows — its parent, so the
   * menu is the crumb's neighbours. `""` is the root. Null only for the
   * ellipsis, which lists its folded folders instead.
   */
  menu: string | null;
  /**
   * The entry the menu marks: the crumb itself. Equal to
   * `stepToward(menu, path)`, which is what the component computes from the
   * open file — this field is the rule written down.
   */
  current: string | null;
  /** Ellipsis only: the folders it stands for, each a submenu. */
  hidden: { label: string; path: string }[];
};

export type CrumbInput = {
  /** The open file, root-relative; null for an empty tab. */
  path: string | null;
  /**
   * Fold the folders into one `…` — a narrow pane. The file survives the
   * fold: it is the crumb that names what is on screen.
   */
  narrow: boolean;
};

export function buildCrumbs({ path, narrow }: CrumbInput): Crumb[] {
  const parts = path ? path.split("/").filter((part) => part !== "") : [];
  if (parts.length === 0) {
    return [];
  }
  const at = (index: number) => parts.slice(0, index + 1).join("/");
  const crumbs: Crumb[] = parts.map((label, index) => {
    const own = at(index);
    return {
      kind: index === parts.length - 1 ? ("file" as const) : ("directory" as const),
      label,
      title: label,
      path: own,
      menu: parentOf(own),
      current: own,
      hidden: [],
    };
  });

  const folders = crumbs.slice(0, -1);
  if (!narrow || folders.length < 2) {
    return crumbs;
  }
  const ellipsis: Crumb = {
    kind: "ellipsis",
    label: "…",
    title: folders.map((folder) => folder.label).join("/"),
    path: folders[folders.length - 1]!.path,
    menu: null,
    current: null,
    hidden: folders.map((folder) => ({ label: folder.label, path: folder.path })),
  };
  return [ellipsis, crumbs[crumbs.length - 1]!];
}

/**
 * The worktree marker, drawn before the crumbs, or null for a tab in the
 * project directory.
 *
 * NOT a crumb: it names the root, and a root has no menu here — its
 * neighbours are outside the project. It is a label, because which copy of
 * the tree a file is in is the one thing a person cannot tell from its name
 * (README, "The explorer's root"), and losing that with the project crumb
 * would have been an accident rather than a decision.
 */
export function worktreeMark(root: ExplorerRoot): { label: string; title: string } | null {
  return root ? { label: root.split(/[\\/]/).pop() ?? root, title: root } : null;
}

export type MenuEntry = {
  path: string;
  name: string;
  kind: "file" | "directory";
  /** The entry on the way to the open file — drawn marked. */
  current: boolean;
};

const COLLATOR = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

/**
 * A listing as a menu: directories first, then files, each in natural
 * order, with the current entry marked. Main sorts a listing this way
 * already; sorting again here is cheap, and makes the menu's order a fact
 * of this module rather than of whichever listing it was handed.
 */
export function menuEntries(entries: readonly DirEntry[], current: string | null): MenuEntry[] {
  return [...entries]
    .sort((left, right) =>
      left.kind !== right.kind ? (left.kind === "directory" ? -1 : 1) : COLLATOR.compare(left.name, right.name),
    )
    .map((entry) => ({ path: entry.path, name: entry.name, kind: entry.kind, current: entry.path === current }));
}

/**
 * The entry in `directory` that lies on the way to `target`: the target
 * itself when it is a direct child, the next folder down when it is deeper,
 * null when it is not under `directory` at all. What every menu marks.
 *
 * For a crumb's own menu this is the crumb — the menu is the crumb's parent,
 * and the crumb is the child of it on the way to the file. Inside a submenu
 * it keeps marking the way down, which is what the ellipsis's folded
 * ancestors need.
 */
export function stepToward(directory: string, target: string | null): string | null {
  if (target === null || target === "") {
    return null;
  }
  if (directory === "") {
    return target.split("/")[0] ?? null;
  }
  if (!target.startsWith(`${directory}/`)) {
    return null;
  }
  const rest = target.slice(directory.length + 1).split("/")[0];
  return rest ? `${directory}/${rest}` : null;
}

/** The directory an entry lives in: `""` at the root. */
export function parentOf(path: string): string {
  const slash = path.lastIndexOf("/");
  return slash < 0 ? "" : path.slice(0, slash);
}

/** The last segment of a root-relative path. */
export function nameOf(path: string): string {
  return path.split("/").pop() ?? path;
}
