import { Extension } from "@tiptap/core";
import Document from "@tiptap/extension-document";
import HardBreak from "@tiptap/extension-hard-break";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import { Placeholder } from "@tiptap/extensions";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import { useEffect, useImperativeHandle, useMemo, useRef, type KeyboardEvent, type Ref } from "react";

import { cn } from "@renderer/lib/utils";

import { ReferenceNode } from "./ReferenceNode";
import { docFromText, inlineContentFromText, textFromDoc } from "./references";

/**
 * The composer's input: a one-paragraph ProseMirror editor over the draft,
 * in which a CAD reference is a chip (`ReferenceNode`) and everything else
 * is text.
 *
 * Why an editor and not the textarea AI Elements ships, and why not a row
 * of chips beside it: a reference belongs *in* the sentence ("make
 * bracket.step#o1.2 thicker"), so it has to be inline, and an inline chip
 * in a textarea is a mirror-and-overlay trick that breaks the moment the
 * chip is wider than the text it stands for. A token list beside the box
 * keeps the textarea but loses the position. ProseMirror already ships in
 * this app (the markdown editor) and gives inline atoms — backspace removes
 * one whole, the arrows select one as a unit — without a line of caret
 * arithmetic. What stays intact is `PromptInput`: its form, its submit,
 * its attachments, its footer. This component replaces only the
 * `<textarea>`, and keeps the one contract the form has with it — a field
 * named `message` — by rendering a hidden textarea whose value is the draft.
 *
 * The draft is the source of truth (the composer store, per session): the
 * editor prints it on every change and re-reads it when it changes from
 * outside — a suggestion card, a slash pick, a reference dropped in by the
 * viewer — comparing serialised text so its own updates are not echoed
 * back into it. Newlines are hard breaks (Shift+Enter), the way the textarea
 * had them; Enter is the caller's (submit).
 */
export type ComposerEditorHandle = {
  focus: () => void;
  /** Empty, as the attachment-removal Backspace rule asks. */
  isEmpty: () => boolean;
  /** The `PromptInput` form the editor sits in, for Enter to submit. */
  form: () => HTMLFormElement | null;
};

export function ComposerEditor({
  value,
  onChange,
  onSubmit,
  onKeyDown,
  onPasteFiles,
  placeholder,
  disabled,
  autoFocus,
  className,
  handle,
}: {
  value: string;
  onChange: (text: string) => void;
  /** Enter, without Shift. The caller decides whether the form can submit. */
  onSubmit: () => void;
  /** First look at every key; `preventDefault` claims it (the slash palette). */
  onKeyDown?: (event: KeyboardEvent) => void;
  /** Files on the clipboard become attachments, as they did in the textarea. */
  onPasteFiles?: (files: File[]) => void;
  placeholder: string;
  disabled?: boolean;
  autoFocus?: boolean;
  className?: string;
  handle?: Ref<ComposerEditorHandle>;
}) {
  // Callbacks are read through refs: the editor keeps its props for its
  // lifetime, and a stale `onSubmit` would send to the wrong session.
  const callbacks = useRef({ onChange, onSubmit, onKeyDown, onPasteFiles });
  useEffect(() => {
    callbacks.current = { onChange, onSubmit, onKeyDown, onPasteFiles };
  });

  const extensions = useMemo(
    () => [
      // Exactly one paragraph: Enter cannot split it, so a stray Enter that
      // reaches the schema does nothing rather than making a second line.
      Document.extend({ content: "paragraph" }),
      Paragraph,
      Text,
      HardBreak,
      ReferenceNode,
      Placeholder.configure({ placeholder, showOnlyWhenEditable: false }),
      Extension.create({
        name: "composerKeys",
        addKeyboardShortcuts() {
          return {
            Enter: () => {
              callbacks.current.onSubmit();
              return true;
            },
          };
        },
      }),
    ],
    [placeholder],
  );

  const editor = useEditor(
    {
      extensions,
      content: docFromText(value),
      editable: !disabled,
      immediatelyRender: false,
      editorProps: {
        attributes: {
          class: "composer-editor min-h-12 max-h-48 overflow-y-auto px-3 py-2.5 text-[13px] leading-5 outline-none",
          role: "textbox",
          "aria-multiline": "true",
          "aria-label": placeholder,
          // What Playwright's `getByPlaceholder` and a person read; the
          // Placeholder extension draws it.
          placeholder,
          "data-composer-input": "",
        },
        handleKeyDown: (_view, event) => {
          callbacks.current.onKeyDown?.(event as unknown as KeyboardEvent);
          return event.defaultPrevented;
        },
        handlePaste: (view, event) => {
          const items = event.clipboardData?.items;
          const files: File[] = [];
          for (const item of items ?? []) {
            if (item.kind === "file") {
              const file = item.getAsFile();
              if (file) {
                files.push(file);
              }
            }
          }
          if (files.length > 0) {
            callbacks.current.onPasteFiles?.(files);
            return true;
          }
          const text = event.clipboardData?.getData("text/plain") ?? "";
          if (!text) {
            return false;
          }
          // Pasted text is read the way typed text is: its references are
          // chips at once, its newlines hard breaks.
          const content = inlineContentFromText(text.replace(/\r\n?/g, "\n"));
          const { from, to } = view.state.selection;
          const nodes = content.map((node) => view.state.schema.nodeFromJSON(node));
          view.dispatch(view.state.tr.replaceWith(from, to, nodes).scrollIntoView());
          return true;
        },
      },
      onUpdate: ({ editor: instance }) => {
        callbacks.current.onChange(textFromDoc(instance.getJSON() as never));
      },
    },
    [extensions],
  );

  // The draft changed from outside: re-read it. Its own updates round-trip
  // to the same text and are left alone.
  useEffect(() => {
    if (!editor || editor.isDestroyed) {
      return;
    }
    if (textFromDoc(editor.getJSON() as never) === value) {
      return;
    }
    editor.commands.setContent(docFromText(value), { emitUpdate: false });
    if (editor.isFocused || value) {
      editor.commands.focus("end");
    }
  }, [editor, value]);

  useEffect(() => {
    editor?.setEditable(!disabled);
  }, [editor, disabled]);

  useEffect(() => {
    if (autoFocus && editor) {
      editor.commands.focus("end");
    }
  }, [autoFocus, editor]);

  useImperativeHandle(
    handle,
    () => ({
      focus: () => editor?.commands.focus("end"),
      isEmpty: () => (editor ? editor.state.doc.textContent === "" && !hasChips(editor) : true),
      form: () => editor?.view.dom.closest("form") ?? null,
    }),
    [editor],
  );

  return (
    <div className={cn("w-full min-w-0 flex-1", className)} data-composer-editor>
      <EditorContent editor={editor} />
      {/* The form's field: `PromptInput` reads `message` off the form on submit. */}
      <textarea aria-hidden className="hidden" name="message" readOnly tabIndex={-1} value={value} />
    </div>
  );
}

function hasChips(editor: Editor): boolean {
  let found = false;
  editor.state.doc.descendants((node) => {
    if (node.type.name === "reference") {
      found = true;
    }
    return !found;
  });
  return found;
}

