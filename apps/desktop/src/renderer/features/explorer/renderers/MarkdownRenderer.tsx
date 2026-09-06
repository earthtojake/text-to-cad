import { MessageResponse } from "@renderer/components/ai-elements/message";

/**
 * A markdown file as a document, which is how Codex opens one — `View source`
 * in the header is the way back to the bytes.
 *
 * The renderer is AI Elements' `MessageResponse`, the same Streamdown that the
 * session transcript renders assistant prose with. That is deliberate: a
 * README opened in the explorer and a README quoted in a thread should not be
 * two different-looking documents, and one component means one set of code
 * blocks, tables and headings to get right.
 *
 * The prose width is capped and centred. A markdown preview stretched across a
 * 900px pane is a wall; 72ch is a column a person reads without moving their
 * head, and it is what makes this look like a document rather than a text
 * field that happens to have bold in it.
 */
export function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div className="h-full overflow-auto" data-selectable>
      <div className="mx-auto w-full max-w-[72ch] px-8 py-8">
        <MessageResponse className="text-[14px] leading-relaxed">{content}</MessageResponse>
      </div>
    </div>
  );
}
