/**
 * The line between two panes: a one-pixel rule with a wider hit area.
 *
 * Ours rather than a resizable-panel library's, because the shell needs
 * exactly one behaviour per pane and the library brought a second collapse
 * state with it. A drag moves the pane's pixels; 40px past the pane's minimum
 * (`PANE_LIMITS.overshoot`) it closes the pane instead — which is a change to
 * the same `collapsed` the toggles write, so a pane going away always leaves
 * a toggle on screen.
 *
 * The keyboard does the same two things: the arrows resize, Enter and Space
 * close. It is a `role=separator` with `aria-valuenow`, which is how the
 * platform describes a splitter. Its value is read in words ("sidebar 280
 * pixels"), and focus on it is drawn wider than the line — a 1px rule is no
 * focus indicator. Enter closes the pane and the shell hands focus to that
 * pane's toggle (`useFocusSurvivesCollapse`).
 */
import { useEffect, useRef } from "react";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";

import { KEYBOARD_STEP_PX, dragOutcome, type SidePane } from "@renderer/lib/panes";
import { PANE_LIMITS } from "@shared/types";

type Gesture = {
  /** Where the pointer went down, and the width at that moment. */
  x: number;
  width: number;
  /** The last width the drag asked for, which is what gets remembered. */
  last: number;
  /** Whether a move has reported a width yet — a click reports none. */
  moved: boolean;
  max: number;
  pane: SidePane;
  onDrag: (width: number) => void;
  onCommit: (width: number) => void;
  onCollapse: () => void;
  onRelease: () => void;
};

export function PaneSeparator({
  pane,
  width,
  min,
  max,
  onDrag,
  onCommit,
  onCollapse,
  onRelease,
}: {
  pane: SidePane;
  /** The pane's current width, which a drag starts from. */
  width: number;
  min: number;
  max: number;
  /** Live, every pointer move: the width to draw with. */
  onDrag: (width: number) => void;
  /** A width to remember: the end of a drag that moved it, or an arrow key. */
  onCommit: (width: number) => void;
  onCollapse: () => void;
  /**
   * The drag is over, however it ended — let go, collapsed, or the separator
   * unmounted under it: stop drawing `onDrag`'s width. Separate from
   * `onCommit` because an arrow key commits without a drag, and a drag that
   * comes back to where it started has nothing to commit but still has to
   * stop being drawn.
   */
  onRelease: () => void;
}) {
  // The whole gesture, captured at pointerdown, rather than read from props
  // while it runs: the listeners are on the window for the length of the drag
  // — the pointer leaves this one-pixel element with its first move — and the
  // callbacks it holds only call store setters, which do not go stale.
  const gesture = useRef<Gesture | null>(null);

  useEffect(() => {
    const end = () => {
      const drag = gesture.current;
      gesture.current = null;
      document.body.style.removeProperty("user-select");
      if (drag?.moved) {
        drag.onRelease();
      }
    };
    const onMove = (event: PointerEvent) => {
      const drag = gesture.current;
      if (!drag) {
        return;
      }
      const delta = event.clientX - drag.x;
      // The sidebar grows to the right of its separator; the explorer grows to
      // the left of its own.
      const requested = drag.pane === "sidebar" ? drag.width + delta : drag.width - delta;
      const outcome = dragOutcome({
        pane: drag.pane,
        requested,
        remembered: drag.width,
        max: drag.max,
      });
      if (outcome.collapsed) {
        // The pane goes now, mid-drag, the way every editor does it — and the
        // gesture ends with it, since the element it was sizing is gone.
        end();
        drag.onCollapse();
        return;
      }
      drag.last = outcome.width;
      drag.moved = true;
      drag.onDrag(outcome.width);
    };
    const onUp = () => {
      const drag = gesture.current;
      if (drag && drag.last !== drag.width) {
        drag.onCommit(drag.last);
      }
      end();
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      // Unmounted mid-drag — the session changed, or the window narrowed past
      // what holds the pane — with no pointerup coming: nothing is committed,
      // since the width belonged to a pane that is no longer the one drawn.
      end();
    };
  }, []);

  // A commit and nothing else: both stores write optimistically, so the new
  // width is drawn at once, and a key is not a drag the shell has to draw.
  const nudge = (by: number) => {
    const next = dragOutcome({ pane, requested: width + by, remembered: width, max });
    if (next.collapsed) {
      onCollapse();
    } else {
      onCommit(next.width);
    }
  };

  return (
    // Named and hinted without a native `title` (the kit's rule, packages/ui/docs/settings-ui.md):
    // a title is no name to a screen reader that reads the separator's value, and it ignores the
    // hint delay. The collapse past the minimum is in the hint.
    <TooltipHint content={`Drag to resize; ${PANE_LIMITS.overshoot}px past its minimum closes it`}>
    <div
      aria-controls={pane}
      aria-label={`Resize the ${pane}`}
      aria-orientation="vertical"
      aria-valuemax={max}
      aria-valuemin={min}
      aria-valuenow={width}
      aria-valuetext={`${pane} ${width} pixels`}
      className="app-no-drag relative z-20 w-px shrink-0 cursor-col-resize bg-border after:absolute after:inset-y-0 after:-left-1 after:w-[9px] after:content-[''] hover:bg-ring/60 focus-visible:bg-ring focus-visible:shadow-[0_0_0_2px_var(--ring)] focus-visible:outline-hidden"
      data-separator={pane}
      onDoubleClick={onCollapse}
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft") {
          event.preventDefault();
          nudge(pane === "sidebar" ? -KEYBOARD_STEP_PX : KEYBOARD_STEP_PX);
        } else if (event.key === "ArrowRight") {
          event.preventDefault();
          nudge(pane === "sidebar" ? KEYBOARD_STEP_PX : -KEYBOARD_STEP_PX);
        } else if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onCollapse();
        }
      }}
      onPointerDown={(event) => {
        if (event.button !== 0) {
          return;
        }
        // No `setPointerCapture`: the listeners are on the window, and a
        // capture on a node that a mid-drag collapse unmounts is a capture
        // nobody releases. Selection is suppressed for the length of the
        // gesture instead, so a drag across the transcript does not highlight
        // it.
        event.preventDefault();
        document.body.style.setProperty("user-select", "none");
        gesture.current = {
          x: event.clientX,
          width,
          last: width,
          moved: false,
          max,
          pane,
          onDrag,
          onCommit,
          onCollapse,
          onRelease,
        };
      }}
      role="separator"
      tabIndex={0}
    />
    </TooltipHint>
  );
}
