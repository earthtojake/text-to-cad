// Copy with code in backticks (src/lib/content.ts), each code span set as code.
export function withCode(text: string) {
  return text.split("`").map((part, index) =>
    index % 2 ? <code key={index} className="font-mono text-foreground">{part}</code> : part,
  );
}
