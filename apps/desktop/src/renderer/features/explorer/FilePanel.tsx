import { PANEL_MAX_WIDTH, PANEL_MIN_WIDTH } from "@renderer/state/explorer";

/**
 * The file tab's panel column: the one frame every panel is drawn in.
 *
 * There is one of these in a file tab and never two, because there is one
 * open panel (`renderers/panels.ts`). Whatever is in it — the file tree, the
 * CAD theme editor, the CAD Inspector — gets the same border, the same
 * width and the same handle, which is the point: they used to be two columns
 * of two designs, the app's tree beside the viewer's own aside, each with its
 * own idea of how wide a panel is.
 *
 * No title bar. Each panel's own top row is its header — the tree's filter,
 * the Inspector's tabs, the theme editor's preset select — and the nav row's
 * toggle is how it closes, the way the viewer's panels have always worked. A
 * title above a tab bar would be a second name for the same thing.
 *
 * A collapsed panel is not rendered at all (the app's pane law), so the
 * toggle for it exists in the document exactly once: in the nav row.
 */
export function FilePanel({
  id,
  label,
  width,
  onWidthChange,
  children,
}: {
  /** The open panel's id, for tests and for styling hooks. */
  id: string;
  /** Names the column for the accessibility tree: the toggle's own label. */
  label: string;
  width: number;
  onWidthChange: (width: number) => void;
  children: React.ReactNode;
}) {
  /**
   * The handle drags the column's left border, so the width is measured from
   * the pane's RIGHT edge — the column is anchored there and the content
   * gives up the room. `parentElement` is the tab's body row, which is that
   * edge; a fragment has no box of its own to measure.
   */
  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const surface = event.currentTarget.parentElement;
    let dragging = true;
    const onMove = (move: PointerEvent) => {
      if (!dragging || !surface) {
        return;
      }
      onWidthChange(surface.getBoundingClientRect().right - move.clientX);
    };
    const onUp = () => {
      dragging = false;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  return (
    <>
      <div
        aria-label={`Resize ${label} panel`}
        aria-orientation="vertical"
        aria-valuemax={PANEL_MAX_WIDTH}
        aria-valuemin={PANEL_MIN_WIDTH}
        aria-valuenow={width}
        className="w-px shrink-0 cursor-col-resize bg-border transition-colors hover:bg-ring data-[dragging=true]:bg-ring"
        onPointerDown={onPointerDown}
        role="separator"
        // A 1px border is the right *look* and a terrible target, so the hit
        // area is widened outward without moving the line.
        style={{ boxShadow: "0 0 0 3px transparent" }}
      />
      <aside
        aria-label={label}
        className="shrink-0 overflow-hidden border-l bg-background"
        data-file-panel-container={id}
        style={{ width }}
      >
        {children}
      </aside>
    </>
  );
}
