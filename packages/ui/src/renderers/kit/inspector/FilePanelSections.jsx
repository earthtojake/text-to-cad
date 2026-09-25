import { createContext, useLayoutEffect, useMemo, useRef, useState } from "react";
import { FileSheetSettingsSection } from "./FileSheet.js";

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
 * heading — the design the Display popover uses. FilePanelTabs also uses this
 * scroller for the active Features/Links or Position tab.
 *
 * Only the column scrolls, never a section inside it, and the Reference for a pick is
 * pinned at the panel's foot, scrolling on its own. With more than one section, each
 * heading folds its section away and back (the Display gates' plus and minus): a view of
 * the panel, and nothing else — a folded section stays mounted and keeps working.
 * Controlled feature gates (`enabled` / `onEnabledChange`) instead disable their effect
 * when closed, and restore defaults through their owning store when reopened.
 *
 * A section's `content` may be a function of whether the panel is on screen, for content
 * that keeps work alive only while it can be seen.
 *
 * @param {{ sections: Array<{ id: string, title: string,
 *   role?: "model" | "position",
 *   content: import("react").ReactNode | ((active: boolean) => import("react").ReactNode),
 *   hideHeading?: boolean, headingAction?: import("react").ReactNode, enabled?: boolean, onEnabledChange?: (enabled: boolean) => void, disabled?: boolean, collapsible?: boolean } | null | false>,
 *   sticky?: boolean, active?: boolean, revealRequest?: { sectionId: string, key: number } | null }} props
 */
export default function FilePanelSections({ sections, active = true, revealRequest = null, sticky = true }) {
  const shown = useMemo(() => sections.filter(Boolean), [sections]);
  const scroller = useRef(null);
  const [pendingReveal, setPendingReveal] = useState(null);
  useLayoutEffect(() => { if (revealRequest) setPendingReveal(revealRequest); }, [revealRequest]);
  const [reference, setReference] = useState(null);
  const [folded, setFolded] = useState(() => new Set());
  const fold = (id, open) => setFolded(previous => {
    const next = new Set(previous);
    if (open) next.delete(id); else next.add(id);
    return next;
  });
  useLayoutEffect(() => {
    if (!active || !pendingReveal) return;
    const section = shown.find(item => item.id === pendingReveal.sectionId);
    if (!section) return;
    // Reveal only changes folding, never a feature gate's enabled state.
    if (folded.has(section.id) && !section.onEnabledChange) {
      fold(section.id, true);
      return;
    }
    const target = scroller.current?.querySelector(`[data-file-panel-section="${CSS.escape(section.id)}"]`);
    if (!target) return;
    const body = target.querySelector('[data-file-panel-body]');
    const header = target.querySelector('[data-file-panel-heading]');
    const offset = (sticky ? shown.findIndex(item => item.id === section.id) + 1 : 1) * (header?.getBoundingClientRect().height || 0);
    const element = scroller.current;
    const top = element.scrollTop + (body || target).getBoundingClientRect().top - element.getBoundingClientRect().top - offset;
    // Use only the natural scroll range. A short section near the end should
    // become visible without manufacturing empty space below it.
    element.scrollTop = Math.max(0, Math.min(top, element.scrollHeight - element.clientHeight));
    setPendingReveal(null);
  }, [active, pendingReveal, folded, shown]);
  return <FilePanelReferenceContext.Provider value={reference}>
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={scroller} className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto" data-file-panel-scroll="">
        {shown.map((section, index) => <FilePanelSection key={section.id} section={section} active={active} index={index} count={shown.length} sticky={sticky}
          alone={shown.length === 1} open={!folded.has(section.id)} onOpenChange={open => fold(section.id, open)} onReveal={() => setPendingReveal({ sectionId: section.id })} />)}
      </div>
      {/* `contents`: what is put here is laid out as this column's own last rows. */}
      <div ref={setReference} className="contents" data-file-panel-reference="" />
    </div>
  </FilePanelReferenceContext.Provider>;
}

function FilePanelSection({ section, active, alone, open, onOpenChange, index, count, onReveal, sticky }) {
  const gated = typeof section.onEnabledChange === "function";
  const collapsible = gated || (!alone && section.collapsible !== false);
  const content = typeof section.content === "function" ? section.content(active) : section.content;
  return <FileSheetSettingsSection title={section.title} hideHeading={section.hideHeading} headingAction={section.headingAction} sectionId={section.id} sticky={sticky} index={index} count={count}
    open={gated ? section.enabled === true : !collapsible || open}
    onOpenChange={collapsible ? gated ? section.onEnabledChange : onOpenChange : undefined}
    gated={gated} disabled={section.disabled} onReveal={onReveal}>{content}</FileSheetSettingsSection>;
}
