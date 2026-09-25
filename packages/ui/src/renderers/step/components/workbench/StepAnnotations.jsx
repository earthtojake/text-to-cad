import { useEffect, useState } from "react";
import { Check, Hash, MessageSquarePlus, Trash2 } from "lucide-react";
import { Button } from "@hardcore/ui/primitives/button";
import { Popover, PopoverContent, PopoverTrigger } from "@hardcore/ui/primitives/popover";
import { TooltipHint } from "@hardcore/ui/primitives/tooltip";
import { cn } from "@hardcore/ui/utils";

// The Select tool's annotations (`workbench/stepAnnotations.js`): the Annotate button beside
// Copy Reference, and the body of the card a dot opens on the model (AnnotationPins.jsx). An
// annotation goes into the chat box as it is made, and reaches the agent only when the person
// sends the prompt. An annotation reaches the
// agent only when the person adds it to the chat box and sends it from there.

const BAR_BUTTON_CLASS = "h-11 gap-1.5 border border-border/60 bg-background/90 px-4 text-sm shadow-lg shadow-black/20 backdrop-blur hover:bg-background";

/** Annotate: a note on the current selection, typed in a small box above the button. */
export function AnnotateButton({ disabled = false, onSubmit }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const submit = () => {
    const value = note.trim();
    if (!value) return;
    onSubmit(value);
    setNote("");
    setOpen(false);
  };
  return (
    <Popover open={open && !disabled} onOpenChange={next => setOpen(next && !disabled)}>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" size="sm" disabled={disabled} className={BAR_BUTTON_CLASS}>
          <MessageSquarePlus className="size-4" aria-hidden="true" />
          Annotate
        </Button>
      </PopoverTrigger>
      <PopoverContent side="top" align="center" sideOffset={10} className="w-80 p-2" aria-label="New annotation"
        onOpenAutoFocus={event => { event.preventDefault(); event.currentTarget.querySelector("textarea")?.focus(); }}>
        <NoteInput value={note} onChange={setNote} onSubmit={submit} onCancel={() => setOpen(false)}
          placeholder="What should change here?" />
        <div className="mt-1.5 flex items-center justify-between gap-2 px-0.5">
          <span className="text-[11px] text-muted-foreground">Enter to add · Shift+Enter for a new line</span>
          <Button type="button" size="sm" className="h-7 px-3 text-xs" disabled={!note.trim()} onClick={submit}>Add</Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function NoteInput({ value, onChange, onSubmit, onCancel, placeholder = "", className = "", label = "Annotation" }) {
  return (
    <textarea aria-label={label} value={value} placeholder={placeholder} rows={2}
      className={cn("w-full resize-none rounded-md border border-input bg-transparent px-2 py-1.5 text-[13px] outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring", className)}
      onChange={event => onChange(event.target.value)}
      onKeyDown={event => {
        // The viewer's own shortcuts (Escape clears the selection, letters pick tools) stay out of the note.
        event.stopPropagation();
        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); onSubmit(); }
        else if (event.key === "Escape") { event.preventDefault(); onCancel(); }
      }} />
  );
}

/** A reference as a chip: pressing it selects that geometry again. */
function ReferenceChip({ reference, onSelect }) {
  return (
    <button type="button" data-annotation-chip={reference.selector} title={reference.selector}
      onClick={event => { event.stopPropagation(); onSelect(); }}
      className="inline-flex max-w-full items-center gap-1 rounded-md border bg-secondary/70 px-1.5 py-0.5 align-middle text-[12px] leading-4 transition-colors hover:bg-secondary">
      <Hash className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="truncate">{reference.label}</span>
    </button>
  );
}

/**
 * One annotation's content: its chips, its note (pressed to edit in place) and its actions.
 * The card a dot opens on the model shows it; adding to the chat is the bar's, for all at once.
 */
export function AnnotationBody({ annotation, index, onSelect, onEdit, onRemove, actions = null }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(annotation.text);
  useEffect(() => { if (!editing) setDraft(annotation.text); }, [annotation.text, editing]);
  const save = () => { const value = draft.trim(); if (value) onEdit(value); setEditing(false); };
  return (
    <div className="flex items-start gap-1.5">
      <div className="min-w-0 flex-1 text-[13px] leading-5">
        <span className="mr-1 font-medium">Annotation {index + 1}:</span>
        {annotation.references.map(reference => (
          <span key={reference.selector} className="mr-1"><ReferenceChip reference={reference} onSelect={onSelect} /></span>
        ))}
        {editing ? (
          <NoteInput className="mt-1" value={draft} onChange={setDraft} onSubmit={save}
            onCancel={() => { setDraft(annotation.text); setEditing(false); }} label={`Edit annotation ${index + 1}`} />
        ) : (
          <button type="button" aria-label={`Edit annotation ${index + 1}`} title="Edit"
            className="rounded-sm text-left whitespace-pre-wrap break-words hover:underline hover:decoration-muted-foreground/50 hover:underline-offset-2"
            onClick={event => { event.stopPropagation(); setEditing(true); }}>
            {annotation.text}
          </button>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-0.5" onClick={event => event.stopPropagation()}>
        {annotation.sent ? (
          <span className="flex items-center gap-0.5 pr-1 text-[11px] text-muted-foreground" aria-label="In the chat box">
            <Check className="size-3" aria-hidden="true" />In chat
          </span>
        ) : null}
        <TooltipHint content="Delete">
          <Button type="button" variant="ghost" size="icon-xs" className="size-6 text-muted-foreground" aria-label={`Delete annotation ${index + 1}`}
            onClick={() => onRemove()}>
            <Trash2 className="size-3.5" />
          </Button>
        </TooltipHint>
        {actions}
      </div>
    </div>
  );
}
