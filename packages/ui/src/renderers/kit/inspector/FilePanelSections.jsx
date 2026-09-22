import { createContext, useId, useState } from "react";
import { cn } from "@hardcore/ui/utils";
import { FILE_SHEET_SECTION_HEADING_CLASSES, FileSheetToggleHeading } from "./FileSheet.js";

/**
 * The panel's foot, where the details of a pick go (`InspectorSplit`): pinned under the
 * sections, so the Reference sits in one place whichever section the pick came from, and
 * never between two of them. `undefined` outside a file's panel; `null` for the moment
 * before the foot is mounted.
 */
export const FilePanelReferenceContext = createContext(undefined);

/** The panel's one scroller: a tree finds it to keep its place across a search. */
export const panelScroller = element => element?.closest("[data-file-panel-scroll]") ?? element;

/**
 * A file's own panel: its sections, stacked tight, each at its own full height under a
 * heading — the design the Display panel's sections use. There are no tabs: the nav row
 * is the tab strip, and a panel is one column of sections.
 *
 * Only the column scrolls, never a section inside it, and the Reference for a pick is
 * pinned at the panel's foot, scrolling on its own. With more than one section, each
 * heading folds its section away and back (the Display gates' plus and minus): a view of
 * the panel, and nothing else — a folded section stays mounted and keeps working.
 *
 * A section's `content` may be a function of whether the panel is on screen, for content
 * that keeps work alive only while it can be seen.
 *
 * @param {{ sections: Array<{ id: string, title: string,
 *   content: import("react").ReactNode | ((active: boolean) => import("react").ReactNode) } | null | false>,
 *   active?: boolean }} props
 */
export default function FilePanelSections({ sections, active = true }) {
  const shown = sections.filter(Boolean);
  const [reference, setReference] = useState(null);
  const [folded, setFolded] = useState(() => new Set());
  const fold = (id, open) => setFolded(previous => {
    const next = new Set(previous);
    if (open) next.delete(id); else next.add(id);
    return next;
  });
  return <FilePanelReferenceContext.Provider value={reference}>
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto" data-file-panel-scroll="">
        {shown.map(section => <FilePanelSection key={section.id} section={section} active={active}
          alone={shown.length === 1} open={!folded.has(section.id)} onOpenChange={open => fold(section.id, open)} />)}
      </div>
      {/* `contents`: what is put here is laid out as this column's own last rows. */}
      <div ref={setReference} className="contents" data-file-panel-reference="" />
    </div>
  </FilePanelReferenceContext.Provider>;
}

function FilePanelSection({ section, active, alone, open, onOpenChange }) {
  const titleId = useId();
  const contentId = useId();
  const content = typeof section.content === "function" ? section.content(active) : section.content;
  // A lone section is the panel's own heading: there is nothing to fold it away beside.
  return <section aria-labelledby={titleId} data-file-panel-section={section.id} className={cn(!alone && "border-b border-border")}>
    {alone ? <h2 id={titleId} className={FILE_SHEET_SECTION_HEADING_CLASSES}>{section.title}</h2>
      : <FileSheetToggleHeading as="h2" title={section.title} open={open} onOpenChange={onOpenChange}
        headingId={titleId} contentId={contentId} verbs={["Expand", "Collapse"]} />}
    <div id={contentId} hidden={!open} className="pb-2">{content}</div>
  </section>;
}
