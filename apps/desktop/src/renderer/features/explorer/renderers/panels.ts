/**
 * The panels a renderer has, and the toggles the file tab draws for them.
 *
 * A file kind that shows something beside its content — markdown's source
 * view, a CAD file's theme editor and file sheet — declares it here, and the
 * nav row draws one icon button per declaration, in declaration order, at
 * the right end of the row immediately LEFT of the files toggle (which stays
 * last and never moves). This is the same shape as the standalone viewer's
 * top bar, where a toggle is highlighted while its panel is open.
 *
 * The tab owns the state, not the renderer, for the same reason it owns
 * `viewSource`: the toggle is in the header and the panel is in the body, and
 * two owners of one flag is how a toggle and a panel come to disagree. A
 * declaration is handed the state it may read and the two setters it may
 * call, and returns what to draw.
 *
 * `traits.panels` is where this reaches `FileTab` (`registry.ts`). There is no
 * per-panel special case in the header: markdown's source toggle is one of
 * these, not the exception it used to be.
 */
import type { LucideIcon } from "lucide-react";

/** One toggle in the nav row, ready to draw. */
export type FilePanel = {
  id: string;
  /** The accessible name and the tooltip — what pressing it does. */
  label: string;
  icon: LucideIcon;
  open: boolean;
  onToggle: () => void;
};

/**
 * What a declaration is given.
 *
 * `viewSource` is the one panel state that persists (it is a field of the
 * tab, so a reload comes back to the same reading of the file); `open` is
 * session state, per open file, keyed by panel id. `ready` is false while
 * the body is not the renderer's own surface — a CAD tab whose runtime did
 * not start shows a failure card, and a toggle over a card that cannot open
 * a panel is a dead control.
 */
export type FilePanelContext = {
  viewSource: boolean;
  setViewSource: (next: boolean) => void;
  open: Readonly<Record<string, boolean>>;
  /**
   * Several flags at once, because a declaration whose panels exclude each
   * other has to close one as it opens the other — in one write, or the
   * record spends a render with two panels open and the toggles disagree
   * with the screen.
   */
  setOpen: (patch: Record<string, boolean>) => void;
  ready: boolean;
};

/** A renderer's panels for one open file. */
export type PanelsFor = (context: FilePanelContext) => FilePanel[];

/**
 * The panel ids. Shared, because the declaration in `registry.ts` names them
 * and the renderer that draws the panels reads the same record.
 */
export const CAD_PANEL = {
  theme: "cad-theme",
  fileSheet: "cad-file-sheet",
} as const;

/**
 * Read one panel's flag out of the tab's record.
 *
 * A missing entry is closed *for the toggle*, which is all this answers. It
 * is not the same as "closed" for the renderer: the CAD pair starts with no
 * entry on purpose, so the viewer's surface still owns the flag and reports
 * what it opened with — the record is read raw there
 * (`openPanels[id] ?? null`) to keep that third state.
 */
export function panelOpen(open: Readonly<Record<string, boolean>>, id: string): boolean {
  return open[id] === true;
}

/**
 * The CAD pair after pressing one of its toggles.
 *
 * They are ONE panel with two contents in the viewer's surface — one width,
 * one resize handle, one inset on the 3D viewport — so opening either closes
 * the other outright, and closing the one you opened leaves nothing open. A
 * press while the OTHER is up opens this one rather than closing something
 * already closed: the gesture reads as "show me this instead".
 *
 * The surface enforces the same rule for the controls it draws itself and
 * reports what it did (`onThemeEditingChange` / `onFileSheetOpenChange`),
 * which is how this record stays in step when the sheet opens on its own —
 * a measurement landing does that. This function is for the presses that
 * start here, where the surface has nothing to report yet.
 */
export function toggleCadPanel(
  open: Readonly<Record<string, boolean>>,
  id: (typeof CAD_PANEL)[keyof typeof CAD_PANEL],
): Record<string, boolean> {
  const other = id === CAD_PANEL.theme ? CAD_PANEL.fileSheet : CAD_PANEL.theme;
  const next = panelOpen(open, other) || !panelOpen(open, id);
  return { [id]: next, [other]: false };
}
