const MARKDOWN_EXTENSIONS = ['md', 'mdx'];

/** Returns true if the file path points to a markdown file. */
export function isMarkdownPath(filePath: string): boolean {
  const ext = filePath.split('.').pop()?.toLowerCase();
  return ext ? MARKDOWN_EXTENSIONS.includes(ext) : false;
}

/** Alias for {@link isMarkdownPath}. */
export const isMarkdownFile = isMarkdownPath;

// ---------------------------------------------------------------------------
// Monaco editor options
// ---------------------------------------------------------------------------

/** Default Monaco editor options shared across all editor instances. */
export const DEFAULT_EDITOR_OPTIONS = {
  minimap: { enabled: true },
  fontSize: 13,
  padding: { top: 12, bottom: 12 },
  lineNumbers: 'on' as const,
  rulers: [],
  wordWrap: 'on' as const,
  automaticLayout: true,
  scrollBeyondLastLine: false,
  renderWhitespace: 'selection' as const,
  cursorBlinking: 'smooth' as const,
  smoothScrolling: true,
  formatOnPaste: true,
  formatOnType: true,
};
