export function formatDiffLineCount(count: number): string {
  if (count < 1000) return String(count);

  return `${Math.floor(count / 1000)}k`;
}
