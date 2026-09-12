import { useEffect, useRef, useState } from "react";

import { cn } from "@hardcore/ui/utils";

/**
 * The field a name is typed into, in place: a rename over a tree row or a
 * crumb, a new file or folder in the tree.
 *
 * Finder's rules. The stem is selected and the extension is not, because
 * renaming `bracket.step` is nearly always about `bracket`. Enter commits,
 * Escape cancels, and clicking away commits — a field left behind with a
 * half-typed name is a worse outcome than a rename the person can undo.
 * The commit hands the name to the caller and stays up until it answers,
 * so a refused name (a slash, a name already taken) is still there to fix.
 *
 * A host with no filesystem never draws one: `rename` and the two `New …`
 * are capabilities (`entry-menu.js`), and a host without them has no item
 * that starts a field.
 *
 * @param {object} props
 * @param {string} props.initial
 * @param {"file"|"directory"} props.kind
 * @param {string} [props.placeholder]
 * @param {string} [props.className]
 * @param {(name: string) => Promise<boolean>} props.onCommit
 *   Resolve true to close the field; false keeps it up with the value intact.
 * @param {() => void} props.onCancel
 * @param {string} [props.label]
 */
export function InlineName({
  initial,
  kind,
  placeholder,
  className,
  onCommit,
  onCancel,
  label = "Name"
}) {
  const [value, setValue] = useState(initial);
  const [busy, setBusy] = useState(false);
  const input = useRef(null);
  // Set by Escape before the blur it causes, so the blur does not commit.
  const cancelled = useRef(false);
  const done = useRef(false);

  useEffect(() => {
    const element = input.current;
    if (!element) {
      return;
    }
    element.focus();
    const dot = kind === "file" ? initial.lastIndexOf(".") : -1;
    element.setSelectionRange(0, dot > 0 ? dot : initial.length);
  }, [initial, kind]);

  const commit = async () => {
    if (done.current || busy) {
      return;
    }
    const name = value.trim();
    if (name === "" || name === initial) {
      done.current = true;
      onCancel();
      return;
    }
    setBusy(true);
    const closed = await onCommit(name);
    setBusy(false);
    if (closed) {
      done.current = true;
    } else {
      input.current?.focus();
      input.current?.select();
    }
  };

  return (
    <input
      aria-label={label}
      className={cn(
        "h-5 min-w-0 flex-1 rounded-sm border border-ring bg-background px-1 text-[13px] text-foreground outline-none",
        busy && "opacity-60",
        className
      )}
      data-inline-name
      disabled={busy}
      onBlur={() => {
        if (!cancelled.current) {
          void commit();
        }
      }}
      onChange={(event) => setValue(event.target.value)}
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => {
        // The tree's own keys (arrows, F2, ⌘⌫) must not act while a name is being typed.
        event.stopPropagation();
        if (event.key === "Enter") {
          event.preventDefault();
          void commit();
        } else if (event.key === "Escape") {
          event.preventDefault();
          cancelled.current = true;
          done.current = true;
          onCancel();
        }
      }}
      placeholder={placeholder}
      ref={input}
      spellCheck={false}
      type="text"
      value={value}
    />
  );
}
