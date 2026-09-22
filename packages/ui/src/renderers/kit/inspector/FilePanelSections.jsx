import { useId } from "react";
import { cn } from "@hardcore/ui/utils";
import { ScrollArea } from "@hardcore/ui/primitives/scroll-area";
import { FILE_SHEET_SECTION_HEADING_CLASSES } from "./FileSheet.js";

/**
 * A file's own panel: its sections, stacked, each under a heading that never
 * collapses — the design the Display panel's sections use. There are no tabs:
 * the nav row is the tab strip, and a panel is one column of sections.
 *
 * A section that FILLS (a tree that scrolls itself and keeps its own filter at
 * the top) takes the height the others leave; the others keep their natural
 * height, scrolling within a share of the panel while one fills. With nothing
 * filling, the panel scrolls as one column. A panel of ONE section has no section
 * of its own: its title heads the panel, and the content follows.
 *
 * A section's `content` may be a function of whether the panel is on screen, for
 * content that keeps work alive only while it can be seen.
 *
 * @param {{ sections: Array<{ id: string, title: string, fill?: boolean,
 *   content: import("react").ReactNode | ((active: boolean) => import("react").ReactNode) } | null | false>,
 *   active?: boolean }} props
 */
export default function FilePanelSections({ sections, active = true }) {
  const shown = sections.filter(Boolean);
  const filling = shown.some(section => section.fill === true);
  const body = shown.map(section => <FilePanelSection key={section.id} section={section} active={active}
    alone={shown.length === 1} filling={filling} />);
  return filling
    ? <div className="flex min-h-0 flex-1 flex-col">{body}</div>
    : <ScrollArea className="min-h-0 flex-1" viewportClassName="h-full">{body}</ScrollArea>;
}

function FilePanelSection({ section, active, alone, filling }) {
  const titleId = useId();
  const fill = section.fill === true;
  const content = typeof section.content === "function" ? section.content(active) : section.content;
  return <section aria-labelledby={titleId} data-file-panel-section={section.id}
    className={cn(!alone && "border-b border-border",
      fill ? "flex min-h-0 flex-1 flex-col" : filling ? "flex max-h-[45%] min-h-0 shrink-0 flex-col" : "pb-2")}>
    <h2 id={titleId} className={cn(FILE_SHEET_SECTION_HEADING_CLASSES, "shrink-0")}>{section.title}</h2>
    {fill ? <div className="flex min-h-0 flex-1 flex-col">{content}</div>
      : filling ? <div className="min-h-0 overflow-y-auto pb-2">{content}</div>
        : content}
  </section>;
}
