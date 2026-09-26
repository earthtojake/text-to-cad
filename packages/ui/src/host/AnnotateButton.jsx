import { useEffect, useRef, useState } from 'react';
import { MessageSquareDot } from 'lucide-react';
import { Button } from '../primitives/button.jsx';
import { Popover, PopoverContent, PopoverTrigger } from '../primitives/popover.jsx';
import { cn } from '@hardcore/ui/utils';

// Annotate: the one way a viewer asks for a note to send with what the person pointed at (a
// selection, a markup). The note is typed in a small box beside the button; what the note is about,
// and where it goes, is the caller's (`useMarkupAnnotate` for a markup, the STEP viewer for geometry).

/**
 * A note's text box: Enter adds it, Shift+Enter is a new line, Escape leaves it.
 * @param {{ value: string, onChange(value: string): void, onSubmit(): void, onCancel(): void, onBlur?(): void,
 *   autoFocus?: boolean, placeholder?: string, className?: string, label?: string }} props
 */
export function NoteInput({ value, onChange, onSubmit, onCancel, onBlur, autoFocus = false, placeholder = '', className = '', label = 'Annotation' }) {
  const ref = useRef(null);
  // Opened to edit a note: the caret goes to its end, so typing carries on from what is there.
  useEffect(() => {
    const element = ref.current;
    if (!autoFocus || !element) return;
    element.focus();
    element.setSelectionRange(element.value.length, element.value.length);
  }, [autoFocus]);
  const onKeyDown = (event) => {
    // The viewer's own shortcuts (Escape clears a selection, letters pick tools) stay out of the note.
    event.stopPropagation();
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); onSubmit(); }
    else if (event.key === 'Escape') { event.preventDefault(); onCancel(); }
  };
  return (
    <textarea ref={ref} aria-label={label} value={value} placeholder={placeholder} rows={2} onBlur={onBlur}
      className={cn('w-full resize-none rounded-md border border-input bg-transparent px-2 py-1.5 text-ui outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring', className)}
      onChange={event => onChange(event.target.value)} onKeyDown={onKeyDown} />
  );
}

/**
 * @typedef {object} AnnotateButtonProps
 * @property {(note: string) => void} onSubmit
 * @property {boolean} [disabled]
 * @property {'bar' | 'toolbar'} [variant] `bar`: the floating action beside a viewport's bottom action; `toolbar`: a compact button in a header.
 * @property {'top' | 'bottom'} [side] Where the note box opens.
 * @property {string} [placeholder]
 */

const VARIANT_CLASS = {
  bar: 'h-11 gap-1.5 border border-border/60 bg-background/90 px-4 text-sm shadow-lg shadow-black/20 backdrop-blur hover:bg-background',
  toolbar: 'h-7 gap-1 px-2 text-sm',
};

/** @param {AnnotateButtonProps} props */
export function AnnotateButton({ onSubmit, disabled = false, variant = 'bar', side = 'top', placeholder = 'What should change here?' }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const submit = () => {
    const value = note.trim();
    if (!value) return;
    onSubmit(value);
    setNote('');
    setOpen(false);
  };
  return (
    <Popover open={open && !disabled} onOpenChange={next => setOpen(next && !disabled)}>
      <PopoverTrigger asChild>
        <Button type="button" variant={variant === 'bar' ? 'outline' : 'ghost'} size="sm" disabled={disabled} className={VARIANT_CLASS[variant]}>
          <MessageSquareDot className={variant === 'bar' ? 'size-4' : 'size-3.5'} aria-hidden="true" />
          Annotate
        </Button>
      </PopoverTrigger>
      <PopoverContent side={side} align="center" sideOffset={10} className="w-80 p-2" aria-label="New annotation"
        onOpenAutoFocus={event => { event.preventDefault(); event.currentTarget?.querySelector('textarea')?.focus(); }}>
        <NoteInput value={note} onChange={setNote} onSubmit={submit} onCancel={() => setOpen(false)} placeholder={placeholder} />
        <div className="mt-1.5 flex items-center justify-between gap-2 px-0.5">
          <span className="text-tiny text-muted-foreground">Enter to add · Shift+Enter for a new line</span>
          <Button type="button" size="sm" className="h-7 px-3 text-xs" disabled={!note.trim()} onClick={submit}>Add</Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
