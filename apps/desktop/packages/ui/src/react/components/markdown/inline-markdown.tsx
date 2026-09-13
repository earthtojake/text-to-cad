function stripMarkdown(text: string): string {
  return text
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/#{1,6}\s+/g, '')
    .replace(/`{3}[\s\S]*?`{3}/g, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/~~([^~]+)~~/g, '$1')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/^\s*>\s+/gm, '')
    .replace(/\n+/g, ' ')
    .trim();
}

export interface InlineMarkdownProps {
  content: string;
  className?: string;
}

/**
 * Renders markdown as stripped plain text — no syntax characters, no line breaks.
 * Intended for compact single-line previews like issue descriptions.
 */
export function InlineMarkdown({ content, className }: InlineMarkdownProps) {
  return <div className={className}>{stripMarkdown(content)}</div>;
}
