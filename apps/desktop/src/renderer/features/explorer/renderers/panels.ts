/**
 * A file tab's panels: the list, and the rule that only one is open.
 *
 * ONE panel column, one width, one border, one resize handle — and a list of
 * things that can be in it: the file tree, and whatever the open file's
 * renderer declares (markdown's source view, a CAD file's theme editor and
 * file sheet). The nav row draws one icon button per panel, in declaration
 * order with the tree last, and highlights the open one; pressing a toggle
 * opens that panel and closes whatever was open. This is the shape the
 * theme editor and the file sheet already had inside the viewer's surface,
 * now the shape of all of them: the tree is an entry in this list, not a
 * second column beside it with a design of its own.
 *
 * The tab owns which one is open, not the renderer and not the surface: the
 * toggle is in the header and the panel is in the body, and two owners of one
 * flag is how a toggle and a panel come to disagree. It is one field of the
 * tab (`FileTabSchema.panel`), so it persists, and it is a single id, so two
 * panels cannot both be open however the writes interleave.
 *
 * `traits.panels` is where a renderer's declarations reach `FileTab`
 * (`registry.ts`); `FilePanel.tsx` is the column they are drawn in.
 */
import type { LucideIcon } from "lucide-react";
import { FolderTree } from "lucide-react";

import { FILE_PANEL_TREE } from "@shared/types";

/**
 * Where a panel's content comes from — which is who draws it.
 *
 * `"tree"` and `"slot"` are both the panel column: the app's own file tree,
 * or a box handed to the file's renderer to draw into (the CAD surface
 * portals its theme editor and its file sheet there, `panelSlot` in the
 * viewer's file-view docs). `"body"` is the one panel that is not a column
 * at all — markdown's source view is the same bytes read differently, so it
 * replaces the content instead of sitting beside it. It is still in this
 * list, and still exclusive with the others: one panel open at a time means
 * opening the source closes the tree.
 */
export type FilePanelContent = "tree" | "slot" | "body";

/** One panel: its toggle in the nav row, and where its content comes from. */
export type FilePanel = {
  id: string;
  /** The accessible name and the tooltip — what pressing it does. */
  label: string;
  icon: LucideIcon;
  content: FilePanelContent;
  /**
   * The panel a tab opens with when the person has not said (`panel: null`).
   * The FIRST declaration that claims it wins, and the tree is last, so a
   * CAD file opens with its file sheet and everything else with the tree.
   */
  defaultOpen?: boolean;
};

/**
 * What a declaration is given.
 *
 * `open` is the id of the open panel, resolved — a declaration reads it to
 * name itself by what pressing it does (`View source` / `View preview`).
 * `ready` is false while the body is not the renderer's own surface: a CAD
 * tab whose runtime did not start shows a failure card, and a toggle over a
 * card that cannot open a panel is a dead control.
 */
export type FilePanelContext = {
  open: string;
  ready: boolean;
};

/** A renderer's panels for one open file. */
export type PanelsFor = (context: FilePanelContext) => FilePanel[];

/**
 * The panel ids a renderer declares. The tree's is `FILE_PANEL_TREE`, in
 * `@shared/types`, because the explorer store names that one too.
 */
export const CAD_PANEL = {
  theme: "cad-theme",
  fileSheet: "cad-file-sheet",
} as const;

/** Markdown's source view — its own id, since the tab's field holds ids. */
export const SOURCE_PANEL = "source";

/**
 * The file tree, as the last entry in every file tab's panel list.
 *
 * A folder-tree glyph rather than a panel one: the button is named by what
 * comes back, not by the fact that a panel slides — a panel icon in a row of
 * file actions reads as a layout control and was skipped over. Last and
 * never moving, so it is the one control in the pane a person can always
 * find in the same place.
 */
export function treePanel(open: string): FilePanel {
  return {
    id: FILE_PANEL_TREE,
    label: open === FILE_PANEL_TREE ? "Hide files" : "Show files",
    icon: FolderTree,
    content: "tree",
    defaultOpen: true,
  };
}

/**
 * Every panel a tab has, in the order the nav row draws them: the renderer's,
 * then the tree.
 */
export function panelsFor(declared: FilePanel[], open: string): FilePanel[] {
  return [...declared, treePanel(open)];
}

/**
 * Which panel is open, given the tab's field and the panels it has.
 *
 * `null` — nobody has said — is the first panel claiming `defaultOpen`.
 * `""` is nothing open, and an id no panel in this list has is nothing open
 * too: a tab that was showing markdown's source and is pointed at a `.step`,
 * or a CAD tab whose surface has not come up, has a field naming a panel
 * that is not there, and the honest answer is that nothing is.
 */
export function resolveOpenPanel(panels: FilePanel[], panel: string | null): FilePanel | null {
  if (panel === null) {
    return panels.find((entry) => entry.defaultOpen) ?? null;
  }
  return panels.find((entry) => entry.id === panel) ?? null;
}

/**
 * The tab's field after pressing one panel's toggle.
 *
 * Opening one closes whatever was open, and pressing the open one closes it
 * — which is the whole rule, because the field is one id. A press while
 * another panel is up reads as "show me this instead" and never blinks the
 * column shut on the way.
 */
export function nextOpenPanel(open: string, id: string): string {
  return open === id ? "" : id;
}
