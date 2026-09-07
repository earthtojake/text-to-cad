/**
 * The file tab's breadcrumb, as data.
 *
 * A crumb is a name and a menu. The project crumb's menu is the root's
 * listing, a folder crumb's menu is that folder's listing, and the file
 * crumb's menu is its siblings — every menu marks the entry that is on the
 * way to the open file, so the menus read as "where am I, and what else is
 * here" from left to right. Picking a file opens it; picking a folder opens
 * a submenu of that folder, the way the CAD Viewer's own breadcrumb does
 * (`apps/viewer/src/client/workbench/breadcrumbs.js`, re-thought here for a
 * tree that is listed one directory at a time).
 *
 * Pure: the component reads listings from the explorer store and draws
 * what this returns, and the unit test reads it directly.
 */
import type { DirEntry } from "@shared/ipc/explorer";
import type { ExplorerRoot } from "@shared/types";

export type CrumbKind = "project" | "worktree" | "directory" | "file" | "ellipsis";

export type Crumb = {
  kind: CrumbKind;
  label: string;
  /** The tooltip: the full segment, or the folded folders joined. */
  title: string;
  /** Root-relative path of what the crumb names; `""` for the root. */
  path: string;
  /**
   * The directory whose listing the crumb's menu shows, or null for a
   * crumb with no menu: the project crumb of a worktree tab (its listing
   * is another root's), and the ellipsis, which lists its folders instead.
   */
  menu: string | null;
  /** The entry the menu marks: the next crumb along, or the file itself. */
  current: string | null;
  /** Ellipsis only: the folders it stands for, each a submenu. */
  hidden: { label: string; path: string }[];
};

export type CrumbInput = {
  projectName: string;
  root: ExplorerRoot;
  /** The open file, root-relative; null for an empty tab. */
  path: string | null;
  /**
   * Fold the folders into one `…` — a narrow pane. The project, the
   * worktree and the file survive the fold: which copy of the tree a file
   * is in is the one thing a person cannot tell from its name.
   */
  narrow: boolean;
};

export function buildCrumbs({ projectName, root, path, narrow }: CrumbInput): Crumb[] {
  const parts = path ? path.split("/").filter((part) => part !== "") : [];
  const at = (index: number) => parts.slice(0, index + 1).join("/");
  const first = parts[0] ?? null;

  const worktree: Crumb | null = root
    ? { kind: "worktree", label: root.split(/[\\/]/).pop() ?? root, title: root, path: "", menu: "", current: first ? at(0) : null, hidden: [] }
    : null;
  const project: Crumb = {
    kind: "project",
    label: projectName,
    title: projectName,
    path: "",
    // In a worktree tab the paths are the worktree's; the project's own
    // listing would be a different tree with the same names in it.
    menu: worktree ? null : "",
    current: worktree || !first ? null : at(0),
    hidden: [],
  };
  const head = worktree ? [project, worktree] : [project];

  if (parts.length === 0) {
    return head;
  }

  const folders = parts.slice(0, -1).map((label, index) => ({
    kind: "directory" as const,
    label,
    title: label,
    path: at(index),
    menu: at(index),
    current: at(index + 1),
    hidden: [],
  }));
  const file: Crumb = {
    kind: "file",
    label: parts[parts.length - 1]!,
    title: parts[parts.length - 1]!,
    path: at(parts.length - 1),
    menu: parts.length > 1 ? at(parts.length - 2) : "",
    current: at(parts.length - 1),
    hidden: [],
  };

  if (!narrow || folders.length < 2) {
    return [...head, ...folders, file];
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
  return [...head, ellipsis, file];
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
