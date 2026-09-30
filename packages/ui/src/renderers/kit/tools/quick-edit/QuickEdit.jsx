import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, Box, Check, MessageCircle, MousePointerClick, X } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { usePromptDestination, useViewerHost } from "../../../../host/context.js";
import { FLOATING_CHROME_SURFACE_CLASS, FLOATING_SURFACE_CLASS } from "../floatingSurface.js";
import { TOOL_PANEL_BUTTON_CLASS, TOOL_PANEL_HEADING_TEXT_CLASS } from "../ToolPanel.jsx";
import { copiedQuickEdit, createQuickEditContext, quickEditSelection, sketchName } from "./quickEditPrompt.js";

const EMPTY = Object.freeze([]);
// The sketch's chip is redrawn once the ink has been still this long, not on every stroke's point.
const THUMBNAIL_DELAY_MS = 350;
const DONE_MS = 1200;
// A selection the person made follows their press in this view; one an agent makes (the live
// controller's `select`) follows none, and opens nothing: it must never take their keyboard.
const PICK_MS = 1500;
const CHIP_CLASS = "inline-flex h-6 min-w-0 max-w-full items-center gap-1 rounded-md border border-border bg-muted/60 px-1.5 text-tiny text-foreground";

const failure = result => (result && (result.status === "failed" || result.status === "cancelled") ? result.message || "The prompt did not go." : "");

/**
 * Quick Edit: a person's note about the file on screen, handed to their agent. A standalone
 * toolbar at the viewer's top-right, its one button a speech bubble; pressed, the box opens under
 * it and takes the keyboard — and it opens itself (and takes the keyboard) when a selection or a
 * sketch begins, so a pick leads straight to saying what should change.
 *
 * What goes with the note is shown as chips on top of it, and it follows the view until a button
 * is pressed: the file (always), how many references are selected (`references`, the selection in
 * the prompt grammar — the references themselves travel, not a picture of them), and the view with
 * its sketch while Draw has ink (`sketch`: present while Draw is up, with `ink` once it has some,
 * and `subscribe` hearing the ink change). The note itself
 * stays as it is written; the X clears it and closes the box, and the toolbar button hides the
 * box with the note kept — and then it stays hidden, opening itself no more, until that button
 * opens it again.
 *
 * The buttons, bottom-right, are the ones this host can carry out, and the rightmost is the
 * primary one, which Enter presses (Shift+Enter is a new line): Copy Prompt always — the note as
 * text for the person to paste into their agent's prompt box, its references as copied references
 * are spelled (`referencePath`) and its sketch saved as a file it names (`host.attachments`);
 * Queue where the destination is a composer (the host's context for the next message); Send where
 * the host can post a message now (`promptContext.send`). Each clears and closes the box once it
 * has gone; a failure keeps the note and says why.
 *
 * @param {{ resource: import("@text-to-cad/core/prompt").ResourceRef,
 *   references?: readonly import("@text-to-cad/core/prompt").PromptReference[],
 *   sketch?: { ink: boolean, capture(): Promise<Blob>, subscribe(listener: () => void): () => void } | null,
 *   referencePath?: (path: string) => string, onCopy?: () => boolean, onEscape?: () => unknown, disabled?: boolean,
 *   className?: string, style?: import("react").CSSProperties }} props
 *   `onCopy`: the viewer's own copy (⌘C / Ctrl+C: the selection's references, or the drawing),
 *   which the key still reaches from the box while none of the note is selected. `onEscape`: the
 *   viewer's own Escape (clearing the selection), which an empty box passes on as it closes; a box
 *   with a note keeps it, and Escape only hands the keyboard back to the view.
 */
export default function QuickEdit({ resource, references = EMPTY, sketch = null, referencePath, onCopy, onEscape, disabled = false, className, style }) {
  const host = useViewerHost();
  const destination = usePromptDestination();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [focusRequest, setFocusRequest] = useState(0);
  const field = useRef(null);
  const root = useRef(null);
  const selection = useMemo(() => quickEditSelection(references), [references]);

  // Opening takes the keyboard, however it opens.
  const reveal = useCallback(() => { setOpen(true); setError(""); setFocusRequest(count => count + 1); }, []);
  useLayoutEffect(() => { if (focusRequest) field.current?.focus({ preventScroll: true }); }, [focusRequest]);
  const openRef = useRef(open);
  openRef.current = open;
  // Put away with its own button, the box stays away until that button opens it again: the
  // person said they did not want it now. Everything else that closes it leaves it to open itself.
  const putAway = useRef(false);
  const autoOpen = useCallback(() => { if (!openRef.current && !putAway.current) reveal(); }, [reveal]);
  const toggle = () => {
    putAway.current = open;
    if (open) setOpen(false); else reveal();
  };
  // The person's presses: a sketch begins mid-stroke, and the box waits for the pen to lift before
  // it takes the keyboard; and a selection opens it only when it follows a press in this view.
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
  // A selection begun (something picked where nothing was) right after the person's press in this
  // view opens the box; so does a sketch begun, below.
  const selecting = selection.length > 0;
  const wasSelecting = useRef(selecting);
  useEffect(() => {
    const began = selecting && !wasSelecting.current;
    wasSelecting.current = selecting;
    if (began && performance.now() - lastPress.current < PICK_MS) autoOpen();
  }, [selecting, autoOpen]);
  // Once per sketch: the first ink of a Draw session, not the ink an Undo takes away and a Redo
  // puts back.
  const drawing = Boolean(sketch);
  const sketching = Boolean(sketch?.ink);
  const sketched = useRef(sketching);
  useEffect(() => {
    if (!drawing) { sketched.current = false; return undefined; }
    if (!sketching || sketched.current) return undefined;
    sketched.current = true;
    if (!pressed.current) { autoOpen(); return undefined; }
    const lifted = () => autoOpen();
    window.addEventListener("pointerup", lifted, { once: true });
    return () => window.removeEventListener("pointerup", lifted);
  }, [drawing, sketching, autoOpen]);

  // The sketch's chip: the view with its ink as it will go, redrawn once the ink is still.
  const [thumbnail, setThumbnail] = useState("");
  const thumbnailUrl = useRef("");
  const showThumbnail = useCallback(url => {
    if (thumbnailUrl.current) URL.revokeObjectURL(thumbnailUrl.current);
    thumbnailUrl.current = url;
    setThumbnail(url);
  }, []);
  useEffect(() => () => { if (thumbnailUrl.current) URL.revokeObjectURL(thumbnailUrl.current); }, []);
  const sketchRef = useRef(sketch);
  sketchRef.current = sketch;
  useEffect(() => {
    if (!open || !sketching) { showThumbnail(""); return undefined; }
    let current = true;
    let timer = 0;
    const redraw = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        Promise.resolve().then(() => sketchRef.current?.capture())
          .then(blob => { if (current && blob) showThumbnail(URL.createObjectURL(blob)); })
          // A chip without its picture is still the sketch's.
          .catch(() => {});
      }, THUMBNAIL_DELAY_MS);
    };
    redraw();
    const stop = sketchRef.current?.subscribe(redraw);
    return () => { current = false; clearTimeout(timer); stop?.(); };
  }, [open, sketching, showThumbnail]);

  useEffect(() => {
    if (!done) return undefined;
    const timer = setTimeout(() => setDone(false), DONE_MS);
    return () => clearTimeout(timer);
  }, [done]);

  const canQueue = destination.kind === "composer" && destination.available;
  const canSend = typeof host.promptContext.send === "function";
  const spell = referencePath || (path => path);
  const fileName = String(resource.kind === "url" ? resource.url : resource.path).split("/").pop();
  const ready = Boolean(text.trim()) && !pending && !disabled;

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
      setText("");
      setOpen(false);
      setDone(true);
    }).catch(caught => setError(caught instanceof Error ? caught.message : String(caught)))
      .finally(() => setPending(""));
  };
  const actions = [
    { id: "copy", label: "Copy Prompt", hint: "Copies this prompt: paste it into your agent's prompt box" },
    canQueue ? { id: "queue", label: "Queue", hint: "Adds this to your next message" } : null,
    canSend ? { id: "send", label: "Send", hint: "Sends this to your agent now" } : null,
  ].filter(Boolean);
  const primary = actions.at(-1).id;

  const clear = () => { setText(""); setError(""); setOpen(false); };
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
      if (!text.trim()) { setOpen(false); setError(""); onEscape?.(); }
    }
  };
  // What is picked, one by one: a reference may name several (`file#o1.1,o1.2`).
  const referenceCount = selection.reduce((count, reference) => count + (reference.target.kind === "cad-selector" ? reference.target.selectors.length : 1), 0);

  return <div ref={root} className={cn("pointer-events-none flex flex-col items-end gap-2", className)} style={style} data-quick-edit="">
    <div role="toolbar" aria-label="Quick Edit" className={cn("pointer-events-auto inline-flex rounded-md p-1", FLOATING_CHROME_SURFACE_CLASS)}>
      <ToolbarButton label="Quick Edit" active={open} aria-pressed={open} aria-expanded={open} disabled={disabled}
        onClick={toggle}>
        {done ? <Check className="size-3.5" aria-hidden="true" /> : <MessageCircle className="size-3.5" aria-hidden="true" />}
      </ToolbarButton>
    </div>
    {open ? <section aria-label="Quick Edit" data-quick-edit-box=""
      // A narrow viewer (a phone) gets it across its whole width, over the tool stack rather than beside it.
      className={cn("pointer-events-auto flex w-[min(20rem,100%)] flex-col gap-1.5 rounded-lg p-2 text-tiny @max-md/cad-viewport:w-full", FLOATING_SURFACE_CLASS)}>
      <div className="flex min-h-5 items-center gap-1">
        <h3 className={cn("min-w-0 flex-1 truncate pl-0.5", TOOL_PANEL_HEADING_TEXT_CLASS)}>Quick Edit</h3>
        <button type="button" aria-label="Clear Quick Edit" className={TOOL_PANEL_BUTTON_CLASS} onClick={clear}>
          <X className="size-3" aria-hidden="true" />
        </button>
      </div>
      {/* What goes with the note, as it is now. */}
      <div className="flex min-w-0 flex-wrap items-center gap-1" aria-label="Attached" data-quick-edit-attachments="">
        <TooltipHint content={spell(resource.kind === "url" ? resource.url : resource.path)}>
          <span className={CHIP_CLASS} data-quick-edit-chip="file"><Box className="size-3 shrink-0 opacity-70" aria-hidden="true" /><span className="min-w-0 truncate">{fileName}</span></span>
        </TooltipHint>
        {referenceCount ? <span className={CHIP_CLASS} data-quick-edit-chip="references">
          <MousePointerClick className="size-3 shrink-0 opacity-70" aria-hidden="true" />{referenceCount} {referenceCount === 1 ? "reference" : "references"}
        </span> : null}
        {sketching ? <span className={cn(CHIP_CLASS, "pl-0.5")} data-quick-edit-chip="sketch">
          {thumbnail ? <img src={thumbnail} alt="" className="h-4.5 w-7 rounded-sm object-cover" /> : <span className="h-4.5 w-7 rounded-sm bg-muted" aria-hidden="true" />}
          Sketch
        </span> : null}
      </div>
      <textarea ref={field} value={text} rows={2} placeholder="Describe your changes" aria-label="Describe your changes"
        className="max-h-40 min-h-14 w-full resize-none rounded-md border border-input bg-background/80 px-2 py-1.5 text-xs leading-5 text-foreground outline-none [field-sizing:content] placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/45"
        onChange={event => { setText(event.target.value); setError(""); }} onKeyDown={onKeyDown} />
      {error ? <p role="alert" className="text-tiny text-destructive">{error}</p> : null}
      <div className="flex items-center justify-end gap-1">
        {actions.map(action => {
          const main = action.id === primary;
          const busy = pending === action.id;
          if (action.id === "send") {
            return <TooltipHint key={action.id} content={action.hint} side="bottom">
              <button type="button" aria-label="Send" disabled={!ready} aria-busy={busy || undefined} onClick={() => run("send")}
                className="flex size-7 shrink-0 items-center justify-center rounded-full bg-foreground text-background transition hover:bg-foreground/85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 disabled:bg-muted-foreground/35 disabled:text-background/80">
                <ArrowUp className="size-4" strokeWidth={2.25} aria-hidden="true" />
              </button>
            </TooltipHint>;
          }
          return <TooltipHint key={action.id} content={action.hint} side="bottom">
            <Button type="button" size="xs" variant={main ? "default" : "ghost"} disabled={!ready} aria-busy={busy || undefined}
              className={cn("h-7 px-2.5 text-xs", !main && "text-muted-foreground hover:text-foreground")} onClick={() => run(action.id)}>
              {action.label}
            </Button>
          </TooltipHint>;
        })}
      </div>
    </section> : null}
  </div>;
}
