import { cn } from "@cad/ui/utils";

/** A panel tab's action button (Params' Reset and Save, Joints' Reset): a panel control, 28px, regular weight. */
export const PANEL_ACTION_CLASS = "h-control shrink-0 px-2 text-ui font-normal";

/**
 * A tab's actions row, the last thing in it (Params' Reset and Save, Joints' Reset): its buttons at the
 * right, the last one's box ending on the panel's right inset (`--panel-inset`: Save fills when there is something to save), directly under the last control (whose own 8px is the gap: a slider's,
 * a field row's) and 8px below them, 8px apart, on the chrome's colour
 * to the panel's edges, kept in sight at the panel's bottom edge while a long tab scrolls under it (sticky),
 * so an action is never scrolled away from what it acts on; under a short tab it stands under the last row.
 * `footProps` go on the sticky foot, the rest on the row.
 */
export function PanelActions({ footProps = null, className, children, ...props }) {
  return <div className="sticky bottom-0 z-10 -mx-(--panel-inset) bg-sidebar px-(--panel-inset)" data-panel-foot="" {...footProps}>
    <div className={cn("flex items-center justify-end gap-2 pb-2", className)} {...props}>{children}</div>
  </div>;
}
