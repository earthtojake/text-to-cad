/**
 * Registry prose with its backticks drawn as code.
 *
 * The ACP registry's descriptions are Markdown-ish — "`opencode acp` serves
 * ACP" — and printed as plain text the backticks show up literally. Only the
 * backtick spans are honoured; nothing else in the text is Markdown here.
 */
export function InlineCode({ text }: { text: string }) {
  const parts = text.split(/`([^`]+)`/);
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <code className="rounded bg-muted px-1 font-mono text-[0.95em]" key={index}>
            {part}
          </code>
        ) : (
          part
        ),
      )}
    </>
  );
}
