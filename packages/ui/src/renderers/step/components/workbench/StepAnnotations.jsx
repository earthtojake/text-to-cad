import { useEffect, useRef, useState } from "react";
import { NoteInput } from "../../../../host/AnnotateButton.js";
import { Hash, Trash2 } from "lucide-react";
import { Button } from "@hardcore/ui/primitives/button";
import { TooltipHint } from "@hardcore/ui/primitives/tooltip";

// The Select tool's annotations (`workbench/stepAnnotations.js`): the Annotate button beside
// Copy Reference (the shared host one), and the body of the card a dot opens on the model
// (AnnotationPins.jsx). An
// annotation goes into the chat box as it is made, and reaches the agent only when the person
// sends the prompt.

/**
 * A reference as a chip, drawn as the chat box draws a reference in the prompt (its frame, and a
 * hash with the label for a selector in the file on screen): pressing it selects that geometry again.
 */
function ReferenceChip({ reference, onSelect }) {
  return (
    <button type="button" data-annotation-chip={reference.selector} title={reference.selector}
      onClick={event => { event.stopPropagation(); onSelect(); }}
      className="inline-flex max-w-full items-center gap-1 rounded-md border bg-secondary/70 px-1.5 py-px align-middle text-[12px] leading-4 text-secondary-foreground transition-colors duration-120 hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <Hash className="size-3 shrink-0 opacity-70" aria-hidden="true" />
      <span className="min-w-0 max-w-[160px] truncate text-muted-foreground">{reference.label}</span>
    </button>
  );
}

/**
 * One annotation's content: its chips, its note (pressed to edit in place) and its actions.
 * It is the body of the card a dot opens on the model.
 */
export function AnnotationBody({ annotation, index, onSelect, onEdit, onRemove, actions = null }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(annotation.text);
  useEffect(() => { if (!editing) setDraft(annotation.text); }, [annotation.text, editing]);
  // Enter, Escape or leaving the box ends an edit, once: the box going away can blur it after.
  const settled = useRef(false);
  const startEditing = () => { settled.current = false; setEditing(true); };
  const save = () => {
    if (settled.current) return;
    settled.current = true;
    const value = draft.trim();
    if (value) onEdit(value);
    setEditing(false);
  };
  const cancel = () => { settled.current = true; setDraft(annotation.text); setEditing(false); };
  return (
    <div className="flex items-start gap-1.5">
      <div className="min-w-0 flex-1 text-[13px] leading-5">
        <span className="mr-1 font-medium">Annotation {index + 1}:</span>
        {annotation.references.map(reference => (
          <span key={reference.selector} className="mr-1"><ReferenceChip reference={reference} onSelect={onSelect} /></span>
        ))}
        {editing ? (
          <NoteInput className="mt-1" value={draft} onChange={setDraft} onSubmit={save} onBlur={save} autoFocus
            onCancel={cancel} label={`Edit annotation ${index + 1}`} />
        ) : (
          <button type="button" aria-label={`Edit annotation ${index + 1}`} title="Edit"
            className="rounded-sm text-left whitespace-pre-wrap break-words hover:underline hover:decoration-muted-foreground/50 hover:underline-offset-2"
            onClick={event => { event.stopPropagation(); startEditing(); }}>
            {annotation.text}
          </button>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-0.5" onClick={event => event.stopPropagation()}>
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

