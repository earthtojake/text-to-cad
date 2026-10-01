import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, Copy, ListPlus, X } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { usePromptDestination, useViewerHost } from "../../../../host/context.js";
import { FLOATING_SURFACE_CLASS } from "../floatingSurface.js";
import { TOOL_PANEL_BUTTON_CLASS } from "../ToolPanel.jsx";
import { copiedQuickEdit, createQuickEditContext, quickEditSelection, sketchName } from "./quickEditPrompt.js";

const EMPTY = Object.freeze([]);
// A press of the person's in this view leads the selection it made; an agent's selection (the live
// controller's `select`) follows none, and opens the box without taking their keyboard.
const PICK_MS = 1500;
// The box's size, as the person drags its corner: its width, and the note's height. A box opens
// 15rem wide, its note growing with what is written.
export const QUICK_EDIT_LIMITS = Object.freeze({ minWidth: 208, maxWidth: 640, minHeight: 56, maxHeight: 320 });
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

const failure = result => (result && (result.status === "failed" || result.status === "cancelled") ? result.message || "The prompt did not go." : "");

/** Each selected reference by its id, one a line: a selector (`o1.1.f2`), or a text range. */
export function quickEditReferenceIds(selection) {
  return selection.flatMap(reference => reference.target.kind === "cad-selector"
    ? reference.target.selectors.map(String)
    : [reference.label || `${reference.target.start.line}:${reference.target.start.column}–${reference.target.end.line}:${reference.target.end.column}`]);
}

/**
 * Quick Edit: a person's note about the file on screen, handed to their agent, in a box at the
 * viewer's top-right that is there only while it has something to say about: nothing shows
 * otherwise. While the note is empty the box follows what it would carry: it opens when something
 * is picked or sketched, and closes when that goes. A written note keeps it open, whatever is
 * picked, until it goes or its X clears it. The X clears everything it would carry too — the
 * selection, as a press on the background would, and the sketch (`onClear`) — and so does a note
 * that has gone. It takes the keyboard for the person — each pick of theirs, or a sketch's first
 * stroke once the pen lifts — never for an agent's selection.
 *
 * Its header names what goes with the note — the selected references (`references`, the selection
 * in the prompt grammar; their ids on hover) and the view with its sketch while Draw has ink
 * (`sketch`). The file always goes and is not named. The buttons, bottom-right, are the ones this
 * host can carry out, the rightmost primary and pressed by Enter (Shift+Enter is a new line): Copy
 * Prompt always — the note as text to paste into an agent's prompt box, its references as copied
 * references are spelled (`referencePath`) and its sketch saved as a file it names
 * (`host.attachments`); Queue where the destination is a composer (the host's context for the next
 * message); Send where the host can post a message now (`promptContext.send`). Each clears and
 * closes the box once it has gone; a failure keeps the note and says why. Its corner resizes it for
 * as long as it is open: the size is the box's own, written to it a frame at a time, so a drag
 * renders nothing, and it goes with the box — the next one opens at the default size.
 *
 * @param {{ resource: import("@text-to-cad/core/prompt").ResourceRef,
 *   references?: readonly import("@text-to-cad/core/prompt").PromptReference[],
 *   sketch?: { ink: boolean, capture(): Promise<Blob> } | null,
 *   referencePath?: (path: string) => string, onCopy?: () => boolean, onEscape?: () => unknown, onClear?: () => void, disabled?: boolean,
 *   hidden?: boolean, className?: string, style?: import("react").CSSProperties }} props
 *   `onCopy`: the viewer's own copy (⌘C / Ctrl+C: the selection's references, or the drawing),
 *   which the key still reaches from the box while none of the note is selected. `onEscape`: the
 *   viewer's own Escape (clearing the selection), which an empty box passes on as it closes; a box
 *   with a note keeps it, and Escape only hands the keyboard back to the view. `hidden`: out of
 *   sight with all it holds (the view is loading).
 */
export default function QuickEdit({ resource, references = EMPTY, sketch = null, referencePath, onCopy, onEscape, onClear, disabled = false,
  hidden = false, className, style }) {
  const host = useViewerHost();
  const destination = usePromptDestination();
  const [text, setText] = useState("");
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const field = useRef(null);
  const box = useRef(null);
  const root = useRef(null);
  const selection = useMemo(() => quickEditSelection(references), [references]);
  const referenceIds = useMemo(() => quickEditReferenceIds(selection), [selection]);
  const sketching = Boolean(sketch?.ink);
  const attached = referenceIds.length > 0 || sketching;
  const written = Boolean(text.trim());
  const open = written || attached;

  // The person's presses: a stroke is under way while one is down, and a pick follows one in this view.
  const pressed = useRef(false);
  const lastPress = useRef(-Infinity);
  useEffect(() => {
    const down = () => { pressed.current = true; };
    // A primary press: a secondary one opens the viewport's menu, which marks what it is about
    // without being a pick to talk about — and the menu keeps the keyboard.
    const up = event => {
      pressed.current = false;
      const view = root.current?.closest("[data-slot=cad-file-view]");
      if (event.button === 0 && view && event.target instanceof Node && view.contains(event.target)) lastPress.current = performance.now();
    };
    window.addEventListener("pointerdown", down, true);
    window.addEventListener("pointerup", up, true);
    window.addEventListener("pointercancel", up, true);
    return () => {
      window.removeEventListener("pointerdown", down, true);
      window.removeEventListener("pointerup", up, true);
      window.removeEventListener("pointercancel", up, true);
    };
  }, []);

  // Opening for the person takes the keyboard: now, and again once the press that opened it has
  // finished, since a view that keeps its own keys focuses itself as a pick lands. A field the
  // person has moved to since keeps it.
  const takeKeyboard = useCallback(() => {
    const focus = () => {
      const note = field.current;
      const active = document.activeElement;
      const typing = active && active !== note && (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.isContentEditable);
      if (note && active !== note && !typing) note.focus({ preventScroll: true });
    };
    focus();
    setTimeout(focus, 0);
  }, []);
  const referenceKey = referenceIds.join("\n");
  const seen = useRef({ referenceKey, sketching });
  useEffect(() => {
    const before = seen.current;
    seen.current = { referenceKey, sketching };
    const picked = referenceIds.length > 0 && referenceKey !== before.referenceKey;
    const inked = sketching && !before.sketching;
    if (!picked && !inked) return undefined;
    // Ink is only ever the person's; a selection is theirs when it follows their press.
    if (!inked && performance.now() - lastPress.current >= PICK_MS) return undefined;
    // A sketch opens it mid-stroke; the keyboard waits for the pen to lift.
    if (pressed.current) {
      const lifted = () => takeKeyboard();
      window.addEventListener("pointerup", lifted, { once: true });
      return () => window.removeEventListener("pointerup", lifted);
    }
    takeKeyboard();
    return undefined;
  }, [referenceKey, sketching, takeKeyboard]);

  const canQueue = destination.kind === "composer" && destination.available;
  const canSend = typeof host.promptContext.send === "function";
  const spell = referencePath || (path => path);
  const ready = written && !pending && !disabled;

  // The note, and everything it would carry: the box goes with them.
  const clearAll = () => { setText(""); setError(""); onClear?.(); };
  // Everything happens inside the press: the host binds its destination (and the clipboard its
  // write) before the picture has finished encoding.
  const run = action => {
    if (!ready) return;
    setError("");
    let outcome;
    try {
      const picture = sketching ? sketch.capture() : null;
      void picture?.catch(() => {});
      const context = createQuickEditContext({ resource, references: selection, text, sketch: picture });
      if (action === "send") outcome = host.promptContext.send(context);
      else if (action === "queue") outcome = host.promptContext.deliver(context);
      else {
        const saved = picture && host.attachments ? picture.then(png => host.attachments.save(png, sketchName(resource))) : Promise.resolve(null);
        outcome = host.clipboard.writeText(saved.then(sketchPath => copiedQuickEdit(context, { referencePath: spell, sketchPath })))
          .then(() => ({ status: "copied" }));
      }
    } catch (caught) { outcome = Promise.reject(caught); }
    setPending(action);
    Promise.resolve(outcome).then(result => {
      const message = failure(result);
      if (message) throw new Error(message);
      clearAll();
    }).catch(caught => setError(caught instanceof Error ? caught.message : String(caught)))
      .finally(() => setPending(""));
  };
  const actions = [
    { id: "copy", label: "Copy Prompt", hint: "Copy prompt", Icon: Copy },
    canQueue ? { id: "queue", label: "Queue", hint: "Add to your next message", Icon: ListPlus } : null,
    canSend ? { id: "send", label: "Send", hint: "Send now", Icon: ArrowUp } : null,
  ].filter(Boolean);
  const primary = actions.at(-1).id;

  const onKeyDown = event => {
    const target = event.currentTarget;
    const copyKey = event.key.toLowerCase() === "c" && (event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey;
    if (copyKey && target.selectionStart === target.selectionEnd) {
      if (onCopy?.()) event.preventDefault();
    } else if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      run(primary);
    } else if (event.key === "Escape") {
      // Back to the model: the viewer's own keys work again. An empty box goes, and the key is the
      // viewer's too; a note is kept, box and all.
      event.preventDefault();
      target.blur();
      target.closest("[data-cad-surface]")?.focus({ preventScroll: true });
      if (!written) onEscape?.();
    }
  };

  // The corner, bottom-left since the box hangs from the top-right: dragging it out grows the box
  // leftward and its note downward. The size is written to the two elements, once a frame, and kept
  // nowhere else: nothing renders under the pointer, and a box that closes takes its size with it.
  const startResize = event => {
    const section = box.current, note = field.current;
    if (event.button !== 0 || !section || !note) return;
    event.preventDefault();
    const handle = event.currentTarget;
    const start = { x: event.clientX, y: event.clientY, width: section.offsetWidth, height: note.offsetHeight };
    handle.setPointerCapture?.(event.pointerId);
    let next = null, frame = 0;
    const draw = () => {
      frame = 0;
      section.style.width = `${next.width}px`;
      note.style.height = `${next.height}px`;
      note.style.maxHeight = "none";
    };
    const move = moved => {
      next = {
        width: clamp(Math.round(start.width + start.x - moved.clientX), QUICK_EDIT_LIMITS.minWidth, QUICK_EDIT_LIMITS.maxWidth),
        height: clamp(Math.round(start.height + moved.clientY - start.y), QUICK_EDIT_LIMITS.minHeight, QUICK_EDIT_LIMITS.maxHeight),
      };
      frame ||= requestAnimationFrame(draw);
    };
    const end = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", end);
      // The last move, if its frame has not come yet.
      if (frame) { cancelAnimationFrame(frame); draw(); }
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  };

  const referenceCount = referenceIds.length;
  return <div ref={root} className={cn("pointer-events-none flex-col items-end", hidden ? "hidden" : "flex", className)} style={style} data-quick-edit="">
    {open ? <section ref={box} aria-label="Quick Edit" data-quick-edit-box=""
      // A narrow viewer (a phone) gets it across its whole width, over the tool stack rather than beside it.
      // It opens in 150ms, animate-in's own: a `duration-*` class would also ease every width a drag
      // writes (the transition is of `all`), and the box would trail its corner.
      className={cn("pointer-events-auto relative flex w-[min(15rem,100%)] max-w-full origin-top-right flex-col gap-2 rounded-lg p-2.5 text-tiny animate-in fade-in-0 zoom-in-95 @max-md/cad-viewport:!w-full",
        FLOATING_SURFACE_CLASS)}>
      <div className="flex min-h-5 min-w-0 items-center gap-2">
        <h3 className="shrink-0 pl-0.5 text-xs font-medium leading-5 text-foreground">Quick Edit</h3>
        {/* What goes with the note, as it is now; the file always does. */}
        <p className="flex min-w-0 flex-1 items-center gap-1.5 truncate text-tiny text-muted-foreground" data-quick-edit-attachments="">
          {referenceCount ? <TooltipHint content={<span className="block whitespace-pre-line text-left">{referenceIds.join("\n")}</span>}>
            <span tabIndex={0} className="rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/45" data-quick-edit-chip="references">
              {referenceCount} {referenceCount === 1 ? "ref" : "refs"}
            </span>
          </TooltipHint> : null}
          {referenceCount && sketching ? <span aria-hidden="true">·</span> : null}
          {sketching ? <span data-quick-edit-chip="sketch">drawing</span> : null}
        </p>
        <button type="button" aria-label="Close Quick Edit" className={TOOL_PANEL_BUTTON_CLASS} onClick={clearAll}>
          <X className="size-3" aria-hidden="true" />
        </button>
      </div>
      {/* It grows with what is written, up to 10rem, until a drag of the corner gives it a height. */}
      <textarea ref={field} value={text} rows={2} placeholder="Describe your changes" aria-label="Describe your changes"
        className="max-h-40 min-h-14 w-full resize-none rounded-md border border-input bg-background/80 px-2 py-1.5 text-xs leading-5 text-foreground outline-none transition-[border-color,box-shadow] [field-sizing:content] placeholder:text-muted-foreground focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:focus:border-blue-400 dark:focus:ring-blue-400/20"
        onChange={event => { setText(event.target.value); setError(""); }} onKeyDown={onKeyDown} />
      {error ? <p role="alert" className="text-tiny text-destructive">{error}</p> : null}
      {/* Buttons of the ordinary shape, all solid: the primary in its colour, the others secondary. */}
      <div className="flex items-center justify-end gap-1.5">
        {actions.map(({ id, label, hint, Icon }) => <TooltipHint key={id} content={hint} side="bottom">
          <Button type="button" variant={id === primary ? "default" : "secondary"} size="icon-sm" className="size-7"
            aria-label={label} disabled={!ready} aria-busy={pending === id || undefined} onClick={() => run(id)} data-quick-edit-action={id}>
            <Icon className="size-3.5" aria-hidden="true" />
          </Button>
        </TooltipHint>)}
      </div>
      <div aria-hidden="true" onPointerDown={startResize} data-quick-edit-resize=""
        className="group/resize absolute bottom-0 left-0 flex size-3.5 cursor-nesw-resize touch-none items-end justify-start p-0.5 @max-md/cad-viewport:hidden">
        <svg viewBox="0 0 8 8" className="size-2 text-muted-foreground/50 group-hover/resize:text-muted-foreground"><path d="M1 2L6 7M1 5L3 7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" fill="none" /></svg>
      </div>
    </section> : null}
  </div>;
}
