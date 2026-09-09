const DEFAULT_MAX_LINES = 4;
const DEFAULT_MAX_CHARS = 300;

/**
 * Returns a short toast-friendly tail of command output (last non-empty lines).
 * Full output should be logged separately for forensics.
 */
export function formatCommandOutputTail(
  output: string,
  options: { maxLines?: number; maxChars?: number } = {}
): string {
  const maxLines = options.maxLines ?? DEFAULT_MAX_LINES;
  const maxChars = options.maxChars ?? DEFAULT_MAX_CHARS;
  const lines = output
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return '';
  const tail = lines.slice(-maxLines).join('\n');
  if (tail.length <= maxChars) return tail;
  return `…${tail.slice(-(maxChars - 1))}`;
}
