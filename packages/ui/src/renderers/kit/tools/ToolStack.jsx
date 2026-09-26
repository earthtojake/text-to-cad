import { useRef, useState } from "react";
import { TOOL_STACK_MIN_WIDTH, clampToolStackWidth } from "./toolStackWidth.js";

const KEY_NUDGE_PX = 16;

/**
 * The tool stack under the strip: one column, the height the viewer leaves it, in which each
 * panel (`ToolPanel.jsx`) takes its natural height until the column runs out. Every panel is the
 * stack's one width. A handle in a small gutter right of the stack widens or narrows all of them
 * together — from its minimum up to half the viewer — by pointer or by keyboard; the width is
 * written back (`onWidthChange`) once the drag lets go, never per pointer move.
 *
 * The column is a size container, so a panel can bound itself by the stack's height (`cqh`),
 * and its width reads the viewport's (`cqw`), so a narrow viewer never draws a stack wider than
 * half of it, whatever width is stored.
 *
 * @param {{ width: number, onWidthChange(width: number): void, hidden?: boolean, children?: import("react").ReactNode }} props
 */
export default function ToolStack({ width, onWidthChange, hidden = false, children }) {
  const [draft, setDraft] = useState(null);
  const drag = useRef(null);
  const column = useRef(null);
  const viewerWidth = () => column.current?.closest("[data-cad-scene-backdrop]")?.getBoundingClientRect().width || window.innerWidth;
  const shown = draft ?? width;
  const commit = next => { setDraft(null); if (next !== width) onWidthChange(next); };
  const stopDrag = event => {
    if (!drag.current || drag.current.pointerId !== event.pointerId) return;
    const next = drag.current.width;
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    commit(next);
  };
  return <div ref={column} hidden={hidden} data-cad-tool-stack="" className="min-h-0 max-w-full flex-1"
    style={{ width: `max(${TOOL_STACK_MIN_WIDTH}px, min(${shown}px, 50cqw))`, containerType: "size" }}>
    <div className="relative flex max-h-full min-h-0 flex-col gap-2">
      {children}
      <div role="separator" tabIndex={0} aria-label="Resize tool panels" aria-orientation="vertical"
        aria-valuemin={TOOL_STACK_MIN_WIDTH} aria-valuemax={clampToolStackWidth(Infinity, viewerWidth())} aria-valuenow={clampToolStackWidth(shown, viewerWidth())}
        data-tool-stack-resize=""
        className="pointer-events-auto absolute inset-y-0 left-full ml-1 w-2 cursor-col-resize touch-none rounded-full outline-none before:absolute before:inset-y-1 before:left-1/2 before:w-0.5 before:-translate-x-1/2 before:rounded-full before:bg-transparent hover:before:bg-ring active:before:bg-ring focus-visible:before:bg-ring"
        onPointerDown={event => {
          if (event.button !== 0) return;
          event.preventDefault();
          drag.current = { pointerId: event.pointerId, left: event.currentTarget.parentElement.getBoundingClientRect().left, width: clampToolStackWidth(shown, viewerWidth()) };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={event => {
          if (drag.current?.pointerId !== event.pointerId) return;
          drag.current.width = clampToolStackWidth(event.clientX - drag.current.left, viewerWidth());
          setDraft(drag.current.width);
        }}
        onPointerUp={stopDrag}
        onPointerCancel={stopDrag}
        onKeyDown={event => {
          const current = clampToolStackWidth(shown, viewerWidth());
          const next = { ArrowLeft: current - KEY_NUDGE_PX, ArrowRight: current + KEY_NUDGE_PX, Home: TOOL_STACK_MIN_WIDTH, End: Infinity }[event.key];
          if (next === undefined) return;
          event.preventDefault();
          commit(clampToolStackWidth(next, viewerWidth()));
        }} />
    </div>
  </div>;
}
