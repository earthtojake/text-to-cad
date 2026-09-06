import { EditorContent, useEditor } from "@tiptap/react";
import { useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@renderer/lib/utils";

import { capturePristine, documentToMarkdown, markdownToDocument } from "../markdown/document";
import { markdownExtensions } from "../markdown/schema";

/**
 * A markdown file as the document it is, and editable in place.
 *
 * It used to be a preview — Streamdown, read-only, with `View source` as the
 * only way to change a word. `View source` is still there and still Monaco;
 * this is the other half, and it is the half a person edits prose in.
 *
 * The look is the preview's: 14px prose in a 72ch column, the app's tokens,
 * the same code chips and headings. What is behind it is different — a
 * ProseMirror document, printed back to markdown by `../markdown/document.ts`,
 * which keeps every block the person did not touch byte for byte.
 *
 * Uncontrolled, like `CodeRenderer` and for the same reason: the file tab owns
 * "what is on disk" and re-mounts this on a reload (`reloadToken`), because
 * pushing new text into a live editor fights the cursor. `onChange` reports
 * the markdown after every edit, which is what makes the tab's dirty dot and
 * `Cmd/Ctrl+S` work exactly as they do for Monaco.
 */
export function MarkdownRenderer({
  content,
  editable = true,
  onChange,
  onSave,
}: {
  content: string;
  editable?: boolean;
  onChange?: (next: string) => void;
  onSave?: () => void;
}) {
  /**
   * Parsed once, on mount, and never again while this editor lives.
   *
   * `content` is the tab's draft, so it changes on every keystroke — deriving
   * the document from it would rebuild the editor under the cursor with every
   * character typed. The file tab re-mounts this component when the file is
   * reloaded (`reloadToken`), and that re-mount is how new text gets in; the
   * same contract `CodeRenderer` has with Monaco.
   */
  const [{ doc, frame }] = useState(() => markdownToDocument(content));

  // `onChange` is called from a callback the editor keeps for its lifetime, so
  // it is read through a ref rather than captured once.
  const notify = useRef(onChange);
  useEffect(() => {
    notify.current = onChange;
  }, [onChange]);

  const editor = useEditor(
    {
      content: doc,
      editable,
      extensions: markdownExtensions,
      editorProps: { attributes: { class: PROSE, spellcheck: "false" } },
      // The renderer is the one writing to the DOM, so TipTap must not also
      // render immediately on mount — React 19 warns about the double write.
      immediatelyRender: false,
      // What "unchanged" means has to be measured in the editor's own terms —
      // see `capturePristine`.
      onCreate: ({ editor: instance }) => capturePristine(frame, instance.getJSON()),
      onUpdate: ({ editor: instance }) => {
        notify.current?.(documentToMarkdown(instance.getJSON(), frame));
      },
    },
    [doc, frame],
  );

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        onSave?.();
      }
    },
    [onSave],
  );

  return (
    <div className="h-full overflow-auto" data-selectable onKeyDown={onKeyDown}>
      <div className="mx-auto w-full max-w-[72ch] px-8 py-8">
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}

/**
 * The document's typography, as one class on the editable element.
 *
 * In the component rather than in a stylesheet because it is this surface's
 * look and nothing else's, and because every value here is an app token — the
 * pane is the same document in light and dark without a second declaration.
 */
const PROSE = cn(
  "min-h-[60vh] text-[14px] leading-relaxed text-foreground outline-none",
  "[&>*:first-child]:mt-0 [&>*:last-child]:mb-0",
  // Headings
  "[&_h1]:mt-8 [&_h1]:mb-4 [&_h1]:text-[1.9em] [&_h1]:font-semibold [&_h1]:tracking-tight",
  "[&_h2]:mt-8 [&_h2]:mb-3 [&_h2]:text-[1.45em] [&_h2]:font-semibold [&_h2]:tracking-tight",
  "[&_h3]:mt-6 [&_h3]:mb-2 [&_h3]:text-[1.15em] [&_h3]:font-semibold",
  "[&_h4]:mt-6 [&_h4]:mb-2 [&_h4]:font-semibold",
  "[&_h5]:mt-4 [&_h5]:mb-2 [&_h5]:font-semibold [&_h6]:mt-4 [&_h6]:mb-2 [&_h6]:font-semibold",
  // Text
  "[&_p]:my-4",
  "[&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2",
  "[&_strong]:font-semibold [&_em]:italic [&_s]:line-through",
  // Code, inline and fenced, in the chips the preview used
  "[&_code]:rounded [&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.85em]",
  "[&_pre]:my-4 [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-muted [&_pre]:p-3 [&_pre]:text-[12.5px] [&_pre]:leading-relaxed",
  "[&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-[inherit]",
  // Lists
  "[&_ul]:my-4 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:my-4 [&_ol]:list-decimal [&_ol]:pl-6",
  "[&_li]:my-1 [&_li>p]:my-0",
  "[&_ul[data-type=taskList]]:list-none [&_ul[data-type=taskList]]:pl-1",
  "[&_li[data-type=taskItem]]:flex [&_li[data-type=taskItem]]:items-baseline [&_li[data-type=taskItem]]:gap-2",
  "[&_li[data-type=taskItem]>label]:shrink-0",
  // Blocks
  "[&_blockquote]:my-4 [&_blockquote]:border-l-2 [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground",
  "[&_hr]:my-8 [&_hr]:border-t",
  "[&_img]:my-2 [&_img]:inline-block [&_img]:max-w-full [&_img]:rounded",
  // Tables
  "[&_table]:my-4 [&_table]:w-full [&_table]:border-collapse [&_table]:text-[13px]",
  "[&_th]:border [&_th]:px-2.5 [&_th]:py-1.5 [&_th]:text-left [&_th]:font-semibold",
  "[&_td]:border [&_td]:px-2.5 [&_td]:py-1.5 [&_td]:align-top",
  // ProseMirror's own affordances
  "[&_.ProseMirror-selectednode]:ring-2 [&_.ProseMirror-selectednode]:ring-ring",
);
