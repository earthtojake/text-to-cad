import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, Check, Copy, ListPlus } from "lucide-react";
import { Button } from "@cad/ui/primitives/button";
import { ScrollArea } from "@cad/ui/primitives/scroll-area";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { cn } from "@cad/ui/utils";
import { promptReferenceIds } from "@cad/core/prompt";
import { usePromptDestination, useViewerHost } from "../../../../host/context.js";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../../../lib/floatingSurface.js";
import { copiedQuickEdit, createQuickEditContext, pastedLines, quickEditSelection } from "./quickEditPrompt.js";
import { insertAtCaret, markSelectedPills, noteText, pasteNodes, selectPillAt } from "./noteEditor.js";
import ReferenceChips from "./ReferenceChips.jsx";
import { useControlUsage } from "../../../../usage/controls.js";
import { useProjectKey } from "../../../../file-viewer/projectKeys.js";
import { useI18n } from "@cad/ui/i18n";

const EMPTY = Object.freeze([]);

// A press of the person's in this view leads the selection it made; an agent's selection (the live
// controller's `select`) follows none, and opens the box without taking their keyboard.
const PICK_MS = 1500;
// The note grows upward with what is written, a line at a time, to four lines (a 20px line, its 6px either side), then
// scrolls; it opens at one line, whatever focuses it. Four, not more: the bar is always over the model.
export const QUICK_EDIT_NOTE_MAX_PX = 4 * 20 + 12;
// The note's scrollbar lane at the bar's inner right edge (the ScrollArea's thin bar, `w-2`).
const SCROLLBAR_LANE_PX = 8;

const failure = (result, unsent) => (result && (result.status === "failed" || result.status === "cancelled") ? result.message || unsent : "");

/** Each selected reference by its ids, one a line, as the prompt grammar names them (`promptReferenceIds`). */
export function quickEditReferenceIds(selection) {
  return selection.flatMap(promptReferenceIds);
}

/**
 * Quick Edit: a person's note about the file on screen, handed to their agent, in a bar at the bottom of the
 * view, on the tool strip's centre line, laid out as a chat's input (the frame places it: `ViewFrame.jsx`'s bottom
 * bar). It is always there, on the tool strip's surface: with nothing to carry, ONE row — the note and its buttons,
 * no close button; with something to carry (its attachments: a selection, an annotation, a
 * measurement), a row of them appears above the note, the bar growing upward, the note where it was. What it carries
 * goes as each chip's X drops it, as the viewer's Escape clears the selection, or as a note queued or sent clears it
 * (`onClear`: the selection and the annotation). It takes the keyboard for the person — each pick of theirs, or an
 * annotation's first stroke once the pen lifts — never for an agent's selection, nor on a phone (`docked`), where the
 * note is a tap away. Its attachments' coming is counted (`quick_edit_shown`).
 *
 * Its attachments are chips: first "Annotation" while Annotate has ink (`annotation`:
 * its X wipes the ink), then the selected references,
 * as the renderer describes them (`chips`,
 * `ReferenceChips.jsx`: as many as fit the row, then "+N more", which shows the rest; each a card of what it is, its picks lit while the
 * pointer is on it, its X dropping them). A renderer that describes none has its references
 * counted on the row instead, their ids on hover (`references`, the selection in the prompt
 * grammar, is what goes either way). The note is plain text, and a reference pasted into it (a
 * line that is one and nothing else, as Copy References writes it, into this file or any other) is
 * a chip in it, where it was pasted: one piece a Backspace takes whole, which the note carries as
 * that reference's text, in its place (`noteEditor.js`). The file always goes and is not named. The buttons, at the note's right on its last line, are the ones this
 * host can carry out, the rightmost primary and pressed by Enter (Shift+Enter is a new line): Copy
 * Prompt always — the note as text to paste into an agent's prompt box, its references by their
 * files' paths from the workspace the host names (`host.promptFiles.folders`; else from `~/`), and the
 * snapshot packet of the views it carries (`prompt.snapshot`: the view on screen and the views with ink, the ink
 * among them), made in the page at the press and pasted inline, without rendering. Every way
 * it goes carries the same. A displayed unsaved or retained revision instead carries explicit
 * context that the saved file may differ, preserving text and references without replay jobs; Queue where the destination is a composer (the host's context for the next
 * message); Send where the host can post a message now (`promptContext.send`). Queue and Send
 * clear the note and what it carried once the note has gone; Copy Prompt keeps it all (nothing has gone yet),
 * its button showing a tick for a moment. A failure keeps the note and says why.
 * The note starts at one line and grows upward as it is written, to four lines (`QUICK_EDIT_NOTE_MAX_PX`), then scrolls.
 *
 * @param {{ resource: import("@cad/core/prompt").ResourceRef,
 *   references?: readonly import("@cad/core/prompt").PromptReference[],
 *   chips?: readonly import("./ReferenceChips.jsx").ReferenceChip[] | null,
 *   annotation?: { present: boolean, clear?: () => void } | null,
 *   prompt?: { snapshot(references: readonly object[]): { views: { label: string }[], annotation?: object | null,
 *     references?: string[] } | null, unavailable?(): string } | null,
 *   nameReference?: ((reference: import("@cad/core/prompt").PromptReference) => string | import("../../inspector/pickGlyph.jsx").CompactName) | null,
 *   notes?: { take(): { text: string, done(): void, cancel?(): void } | null } | null,
 *   onCopy?: () => boolean, onEscape?: () => unknown, onClear?: () => void, disabled?: boolean,
 *   hidden?: boolean, docked?: boolean, className?: string, style?: import("react").CSSProperties }} props
 *   `docked`: a phone's: the same bar across the view (its sizes the scale's, `globals.css`), the keyboard left down.
 *   `prompt.snapshot(references)`: what the packet is made of, read as the press finds the view, the selection
 *   given (a board's packet names what is picked in it, which a snapshot lights), or null where there is no view.
 *   `nameReference`: what the renderer calls a reference into the file on screen, for its chip in
 *   the note ("cam"); "" where it has no name for it, which then reads as its file and ids.
 *   `notes`: what the renderer has to tell the agent with the next message, asked at the press
 *   (`take()`: its text, or null for nothing): it goes after what the person wrote, however the
 *   message goes (copied, queued or sent), and once it has gone the renderer is told (`done()`), so
 *   it is said once. A message that failed hands it back (`cancel()`) for the next; until one of
 *   the two, `take()` gives it to no other message. It opens no box by itself.
 *   `onCopy`: the viewer's own copy (⌘C / Ctrl+C: the selection's references, or the annotation),
 *   which the key still reaches from the box while none of the note is selected. `onEscape`: the
 *   viewer's own Escape (clearing the selection, and so the attachments), which an empty box passes on; a box
 *   with a note keeps it, and Escape only hands the keyboard back to the view. `hidden`: out of
 *   sight with all it holds (the view is loading).
 */
export default function QuickEdit({ resource, references = EMPTY, chips = null, annotation = null, prompt = null, nameReference = null, notes = null, onCopy, onEscape, onClear, disabled = false,
  hidden = false, docked = false, className, style }) {
  const { t } = useI18n();
  const host = useViewerHost();
  const controls = useControlUsage();
  const destination = usePromptDestination();
  const [text, setText] = useState("");
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const field = useRef(null);
  const box = useRef(null);
  const root = useRef(null);
  const selection = useMemo(() => quickEditSelection(references), [references]);
  const referenceIds = useMemo(() => quickEditReferenceIds(selection), [selection]);
  const annotated = Boolean(annotation?.present);
  const attached = referenceIds.length > 0 || annotated;
  const written = Boolean(text.trim());
  const replayUnavailable = prompt?.unavailable?.() || "";
  // Counted as its attachments come (`quick_edit_shown`): how often it has something to carry.
  const shownBefore = useRef(false);
  useEffect(() => {
    if (attached && !hidden && !shownBefore.current) controls.used("quick_edit_shown");
    shownBefore.current = attached && !hidden;
  }, [attached, hidden, controls]);

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
  // person has moved to since keeps it. On a phone a pick leaves the keyboard down: the note is a tap away.
  // The keyboard is lent (`lent`) until the person writes in the note, presses in it or leaves it: till then
  // its `[` and `]` are still the view's, the folder's previous and next document (`projectKeys.js`).
  const lent = useRef(false);
  const takeKeyboard = useCallback(() => {
    if (docked) return;
    const focus = () => {
      const note = field.current;
      const active = document.activeElement;
      const typing = active && active !== note && (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.isContentEditable);
      if (note && active !== note && !typing) { lent.current = true; note.focus({ preventScroll: true }); }
    };
    focus();
    setTimeout(focus, 0);
  }, [docked]);
  const referenceKey = referenceIds.join("\n");
  const seen = useRef({ referenceKey, annotated });
  useEffect(() => {
    const before = seen.current;
    seen.current = { referenceKey, annotated };
    const picked = referenceIds.length > 0 && referenceKey !== before.referenceKey;
    // Ink is only ever the person's; a selection is theirs when it follows their press.
    const inked = annotated && !before.annotated;
    if (!picked && !inked) return undefined;
    if (!inked && performance.now() - lastPress.current >= PICK_MS) return undefined;
    // An annotation opens it mid-stroke; the keyboard waits for the pen to lift.
    if (pressed.current) {
      const lifted = () => takeKeyboard();
      window.addEventListener("pointerup", lifted, { once: true });
      return () => window.removeEventListener("pointerup", lifted);
    }
    takeKeyboard();
    return undefined;
  }, [referenceKey, annotated, takeKeyboard]);

  // A pill the selection takes in is highlighted as its text is: it shows no selection of its own.
  useEffect(() => {
    const mark = () => markSelectedPills(field.current);
    document.addEventListener("selectionchange", mark);
    return () => document.removeEventListener("selectionchange", mark);
  }, []);

  const canQueue = destination.kind === "composer" && destination.available;
  const canSend = typeof host.promptContext.send === "function";
  const ready = written && !pending && !disabled;

  // The note, and everything it would carry: the box goes with them.
  const clearAll = () => { setText(""); field.current?.replaceChildren(); setError(""); onClear?.(); };
  // A copied prompt has gone nowhere yet: the box keeps it, and its button says it was copied.
  const [copied, setCopied] = useState(false);
  const copiedTimer = useRef(0);
  useEffect(() => () => clearTimeout(copiedTimer.current), []);
  const showCopied = () => {
    clearTimeout(copiedTimer.current);
    setCopied(true);
    copiedTimer.current = setTimeout(() => setCopied(false), 1600);
  };
  // Everything happens inside the press: the views are read as they are and their packet made, and the host binds
  // its destination (and the clipboard its write) before the folders its files are named by are known.
  const run = action => {
    if (!actionReady(action)) return;
    setError("");
    let outcome;
    // What the renderer adds to this message (`notes`), told it has gone once the message has.
    let note = null;
    try {
      note = notes?.take?.() ?? null;
      const unavailable = prompt?.unavailable?.() || "";
      // The selection goes with the views: a board's packet lights what it names when it is drawn again.
      const snapshot = unavailable ? null : prompt?.snapshot?.(selection) ?? null;
      // The folders the message names its files by, asked at the press (a browser's workspace is its last launch's).
      const folders = host.promptFiles?.folders?.() ?? null;
      void folders?.catch(() => {});
      const context = createQuickEditContext({ resource, references: selection, text, snapshot, viewUnavailable: unavailable, folders,
        notes: note?.text ? [note.text] : [], subject: host.promptSubject });
      if (action === "send") outcome = host.promptContext.send(context);
      else if (action === "queue") outcome = host.promptContext.deliver(context);
      else outcome = host.clipboard.writeText(copiedQuickEdit(context)).then(() => ({ status: "copied" }));
    } catch (caught) { outcome = Promise.reject(caught); }
    setPending(action);
    Promise.resolve(outcome).then(result => {
      const message = failure(result, t("quickEdit.notSent"));
      if (message) throw new Error(message);
      note?.done?.();
      try { host.usage?.used("quickEdit"); } catch { /* counting a use never fails it */ }
      controls.used(`quick_edit_${action}`);
      if (action === "copy") showCopied();
      else clearAll();
    }).catch(caught => {
      // The message did not go: what the renderer added to it is the next message's (`cancel`).
      try { note?.cancel?.(); } catch { /* a note handed back never fails the message's error */ }
      setError(caught instanceof Error ? caught.message : String(caught));
    }).finally(() => setPending(""));
  };
  const actions = [
    { id: "copy", label: t("quickEdit.copyPrompt"), hint: t("quickEdit.copyPromptHint"), Icon: Copy },
    canQueue ? { id: "queue", label: t("quickEdit.queue"), hint: t("quickEdit.queueHint"), Icon: ListPlus } : null,
    canSend ? { id: "send", label: t("quickEdit.send"), hint: t("quickEdit.sendHint"), Icon: ArrowUp } : null,
  ].filter(Boolean);
  const primary = actions.at(-1).id;
  // Copy needs no note (the selection, the annotation and the views go as they are); Queue and Send do.
  const actionReady = id => (id === "copy" ? !pending && !disabled : ready);
  // The note's buttons at its right, on its last line: an icon each, its name in its tooltip and as its accessible
  // name ("Copy Prompt"), the last the primary — Copy Prompt alone in a host that takes no message, as the web. The
  // control, the toolbar's tiles, the step apart (THE scale, `globals.css`: a phone's the same class at its tokens).
  const size = "size-control";
  const glyph = "size-glyph-sm";
  const ctas = () => actions.map(({ id, label, hint, Icon }) => <TooltipHint key={id} content={id === "copy" && actions.length === 1 ? label : hint} side="top">
      <Button type="button" variant={id === primary ? "default" : "secondary"} size="icon-sm" className={size}
        aria-label={id === "copy" && copied ? t("quickEdit.promptCopied") : label} disabled={!actionReady(id)} aria-busy={pending === id || undefined} onClick={() => run(id)} data-quick-edit-action={id}>
        {id === "copy" && copied ? <Check className={glyph} aria-hidden="true" /> : <Icon className={glyph} aria-hidden="true" />}
      </Button>
    </TooltipHint>);

  // The room the note keeps clear at its right on every line: its buttons (the control each, the step apart: THE scale's
  // tokens, so a phone's follows the switch), 6px, and the scrollbar's lane; and whether it scrolls now (its buttons then
  // step left of the scrollbar).
  const reserve = `calc(${actions.length} * var(--cad-control) + ${actions.length - 1} * var(--cad-step) + ${6 + SCROLLBAR_LANE_PX}px)`;
  const noteViewport = useRef(null);
  const [scrolling, setScrolling] = useState(false);
  useLayoutEffect(() => {
    const viewport = noteViewport.current;
    setScrolling(Boolean(viewport && viewport.scrollHeight > viewport.clientHeight + 1));
  }, [text]);

  // What is written, read back from the field: its text, each chip its reference. An emptied field
  // is emptied of what an editor leaves behind (a stray line break), so its placeholder shows.
  const readNote = note => {
    const value = noteText(note);
    if (!value.trim() && note.childNodes.length && !note.querySelector("[data-quick-edit-note-ref]")) note.replaceChildren();
    setText(value);
    setError("");
  };
  // A paste is the note's to place: plain text, and each line that is a reference a chip, at the caret.
  const onPaste = event => {
    event.preventDefault();
    const note = event.currentTarget;
    insertAtCaret(note, pasteNodes(pastedLines(event.clipboardData?.getData("text/plain"), copiedChips.current), note.ownerDocument, nameReference, t("quickEdit.annotation")));
    readNote(note);
  };

  // A click on a pill selects it whole, as a double-click does a word: a Backspace takes it. Any press in the note
  // is the person's own: the keyboard is no longer lent.
  const onNoteMouseDown = event => {
    lent.current = false;
    if (event.button !== 0 || event.shiftKey) return;
    const note = event.currentTarget;
    if (!event.target?.closest?.("[data-quick-edit-note-ref]")) return;
    event.preventDefault();
    note.focus({ preventScroll: true });
    selectPillAt(note, event.target);
  };

  const projectKey = useProjectKey();
  const onKeyDown = event => {
    const target = event.currentTarget;
    // A note a pick lent the keyboard to, still empty: `[` and `]` step through the folder, as in the view.
    if (lent.current && !written && !event.metaKey && !event.ctrlKey && !event.altKey && !event.repeat && !event.nativeEvent.isComposing
      && projectKey(event.nativeEvent)) {
      event.preventDefault();
      return;
    }
    const copyKey = event.key.toLowerCase() === "c" && (event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey;
    if (copyKey && (target.ownerDocument.getSelection?.()?.isCollapsed ?? true)) {
      if (onCopy?.()) event.preventDefault();
    } else if (event.key === "Enter" && !event.nativeEvent.isComposing) {
      event.preventDefault();
      // Shift+Enter is a new line, as plain text has it: the browser's own line break, which keeps a line
      // at the note's end to stand the caret on (a bare "\n" there draws none, and the next key lands
      // before it); a node of our own where the browser has no editing commands.
      if (event.shiftKey) {
        if (!target.ownerDocument.execCommand?.("insertLineBreak")) insertAtCaret(target, [target.ownerDocument.createTextNode("\n")]);
        readNote(target);
      }
      else run(primary);
    } else if (event.key === "Escape") {
      // Back to the model: the viewer's own keys work again. In an empty box the key is the viewer's too (the
      // selection, and so the attachments, go); a note is kept.
      event.preventDefault();
      target.blur();
      target.closest("[data-cad-surface]")?.focus({ preventScroll: true });
      if (!written) onEscape?.();
    }
  };

  // The annotation chip describes the prompt's data; only selection chips copy references. A renderer that hands
  // no chips has its references drawn as chips of their own, grouped as every other (`reference`).
  const ownChips = useMemo(() => (chips ? chips : referenceIds.map(id => ({ key: `reference:${id}`, label: id, group: "reference" }))), [chips, referenceIds]);
  const wipe = annotation?.clear;
  const annotationChip = useMemo(() => (annotated ? {
    key: "annotation", label: t("quickEdit.annotation"), glyph: "pencil",
    ...(wipe ? { onRemove: wipe } : {})
  } : null), [annotated, wipe, t]);
  // The chips stand in the order they came — picked or drawn — whatever their kind: each keeps the
  // place it first took, and one that goes and comes back takes a new one at the end.
  const order = useRef(new Map());
  const copiedChips = useRef(new Map());
  const shownChips = useMemo(() => {
    const all = [annotationChip, ...ownChips].filter(Boolean);
    const seen = order.current;
    const keys = new Set(all.map(chip => chip.key));
    for (const key of [...seen.keys()]) if (!keys.has(key)) seen.delete(key);
    for (const chip of all) if (!seen.has(chip.key)) seen.set(chip.key, seen.size ? Math.max(...seen.values()) + 1 : 0);
    // What each copies is kept as it goes, so a paste of it into the note is its pill (`pastedLines`).
    return all.sort((a, b) => seen.get(a.key) - seen.get(b.key)).map(chip => (typeof chip.copy === "function" ? { ...chip, copy: async () => {
      const value = await chip.copy();
      if (value) copiedChips.current.set(String(value).trim(), chip);
      return value;
    } } : chip));
  }, [annotationChip, ownChips]);
  const section = <section ref={box} aria-label={t("quickEdit.title")} data-quick-edit-box=""
      // The bar: the toolbar's shape, a chat's input — its attachments on a row over the note when it has any, the note
      // with its buttons at its right.
      className={cn("@container/quick-edit pointer-events-auto relative flex w-full flex-col gap-1 text-xs",
        FLOATING_CHROME_SURFACE_CLASS, "rounded-[calc(var(--cad-radius-control)+6px)] p-[5px]",
        "transition-[border-color,box-shadow,background-color] focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/20")}
      data-docked={docked ? "" : undefined}>
      {/* Its attachments, where it has any: the chips (the annotation's, the picks'), one a kind ("5 parts", or a single
          pick's name), one row, the rest under "+N more"; each its own X. */}
      {shownChips.length ? <div className="flex min-h-icon-button min-w-0 items-center gap-1.5 pl-1" data-quick-edit-context="">
        <ReferenceChips chips={shownChips} rows={1} grouped className="min-w-0 flex-1" />
      </div> : null}
      {replayUnavailable ? <p role="status" className="px-1 text-xs text-muted-foreground" data-quick-edit-replay-unavailable="">{replayUnavailable}</p> : null}
      {/* Its input: plain text with references inline, one comfortable line to start, growing upward a line at a time
          as it is written (not as it is focused) to four, then scrolling in the chrome's ScrollArea. The note spans the
          bar's width, so its scrollbar stands at the bar's inner right edge; its buttons stand at its bottom-right, in
          room the note keeps clear on every line (their width, its 6px, and the scrollbar's lane), so no text runs under
          them, and while it scrolls they stand left of the scrollbar's lane, never over its thumb. */}
      <div className="relative min-w-0" data-quick-edit-compose="">
        <ScrollArea data-quick-edit-note-box="" className="w-full min-w-0" style={{ maxHeight: QUICK_EDIT_NOTE_MAX_PX }} viewportRef={noteViewport}>
          <div ref={field} role="textbox" aria-multiline="true" aria-label={t("quickEdit.describeLabel")} tabIndex={0}
            contentEditable="plaintext-only" suppressContentEditableWarning data-placeholder={t("quickEdit.describe")} data-quick-edit-note=""
            style={{ paddingRight: reserve }}
            className={cn("w-full whitespace-pre-wrap break-words py-1.5 pl-1.5 text-foreground outline-none empty:before:pointer-events-none empty:before:text-muted-foreground empty:before:content-[attr(data-placeholder)]",
              // What a person types (and its placeholder) at the chrome's UI size, as a field's text is, docked or floating;
              // the size before the 20px lines: cn() lets a later font size drop an earlier leading.
              "min-h-[max(2rem,var(--cad-control))] text-ui leading-5")}
            onInput={event => { lent.current = false; readNote(event.currentTarget); }} onBlur={() => { lent.current = false; }} onKeyDown={onKeyDown} onPaste={onPaste} onMouseDown={onNoteMouseDown} />
        </ScrollArea>
        <div className="absolute flex items-center gap-1" style={{ right: scrolling ? SCROLLBAR_LANE_PX : 0, bottom: "calc((max(2rem, var(--cad-control)) - var(--cad-control)) / 2)" }} data-quick-edit-actions="">{ctas()}</div>
      </div>
      {error ? <p role="alert" className="px-1 text-xs text-destructive">{error}</p> : null}
    </section>;
    return <div ref={root} className={cn("pointer-events-none w-full shrink-0 flex-col items-center", hidden ? "hidden" : "flex", className)} style={style} data-quick-edit="">
    {section}
  </div>;
}
