/**
 * What shared editors need to know, with nothing loaded to know it.
 *
 * Split from `monaco-setup.ts` on purpose: that module imports the whole of
 * `monaco-editor` and its five workers for their side effects, and this one is
 * a lookup table and an options object. Anything that only wants "what
 * language is this file" — the file tab's header, a test — should not pull two
 * megabytes of editor in to find out.
 */
import type { editor } from "monaco-editor";

export const MONACO_LIGHT = "text-to-cad-light";
export const MONACO_DARK = "text-to-cad-dark";

/**
 * The transcript's variants: the same colours on a transparent background, so
 * a diff in a reply sits on the transcript itself. Names of their own — a
 * second `defineTheme` under the shell theme's name replaces it for every
 * editor in the window, which is how the review once lost its colours.
 */
export const MONACO_TRANSCRIPT_LIGHT = "text-to-cad-transcript-light";
export const MONACO_TRANSCRIPT_DARK = "text-to-cad-transcript-dark";

export function monacoTheme(resolved: "light" | "dark"): string {
  return resolved === "dark" ? MONACO_DARK : MONACO_LIGHT;
}

export function transcriptMonacoTheme(resolved: "light" | "dark"): string {
  return resolved === "dark" ? MONACO_TRANSCRIPT_DARK : MONACO_TRANSCRIPT_LIGHT;
}

/**
 * Extension → Monaco language id.
 *
 * Monaco's own registry does this by filename, but only for the languages its
 * default build registers; this table is the app's answer for the ones that
 * matter here, with `plaintext` as the honest fallback. A wrong guess is worse
 * than none — it colours a file as something it is not.
 */
const LANGUAGES: Record<string, string> = {
  ts: "typescript",
  tsx: "typescript",
  mts: "typescript",
  cts: "typescript",
  js: "javascript",
  jsx: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  json: "json",
  jsonc: "json",
  json5: "json",
  ipynb: "json",
  md: "markdown",
  markdown: "markdown",
  mdx: "markdown",
  css: "css",
  scss: "scss",
  less: "less",
  html: "html",
  htm: "html",
  xml: "xml",
  svg: "xml",
  urdf: "xml",
  srdf: "xml",
  sdf: "xml",
  yml: "yaml",
  yaml: "yaml",
  toml: "ini",
  ini: "ini",
  cfg: "ini",
  conf: "ini",
  py: "python",
  pyi: "python",
  rs: "rust",
  go: "go",
  c: "c",
  h: "c",
  cc: "cpp",
  cpp: "cpp",
  cxx: "cpp",
  hpp: "cpp",
  java: "java",
  kt: "kotlin",
  swift: "swift",
  rb: "ruby",
  php: "php",
  sh: "shell",
  bash: "shell",
  zsh: "shell",
  fish: "shell",
  sql: "sql",
  graphql: "graphql",
  gql: "graphql",
  dockerfile: "dockerfile",
  lua: "lua",
  r: "r",
  csv: "plaintext",
  txt: "plaintext",
  log: "plaintext",
};

/** The Monaco language for a path, `plaintext` when there is no good answer. */
export function languageFor(filePath: string): string {
  const name = filePath.split("/").pop() ?? filePath;
  const base = name.toLowerCase();
  if (base === "dockerfile" || base.startsWith("dockerfile.")) {
    return "dockerfile";
  }
  if (base === "makefile") {
    return "plaintext";
  }
  // A dotfile's extension is its name: `.gitignore` -> `gitignore`.
  const extension = base.includes(".") ? (base.split(".").pop() ?? "") : "";
  return LANGUAGES[extension] ?? "plaintext";
}

/**
 * One Monaco model per mounted view, with source and document identity in the
 * URI. The same view keeps its model across React renders, while two viewers
 * opening an identical path cannot share edits or cursor state.
 */
export function monacoModelUri(
  sourceId: string,
  filePath: string,
  documentKey: string,
  viewId: string,
): string {
  const encoded = [sourceId, filePath, documentKey, viewId].map((part) =>
    encodeURIComponent(part),
  );
  return `text-to-cad-file://model/${encoded.join("/")}`;
}

/** Before Settings has written `--font-mono`, and in a test with no stylesheet. */
const FALLBACK_CODE_FONT =
  'ui-monospace, "SF Mono", SFMono-Regular, Menlo, Monaco, "Cascadia Mono", Consolas, monospace';

/**
 * Settings' Code font, which `use-appearance.ts` writes to `--font-mono` on
 * <html>. Resolved to the family itself, not `var(--font-mono)`: Monaco
 * measures glyphs on a canvas, and a canvas does not resolve variables.
 */
export function codeFontFamily(): string {
  if (typeof document === "undefined") return FALLBACK_CODE_FONT;
  return getComputedStyle(document.documentElement).getPropertyValue("--font-mono").trim() || FALLBACK_CODE_FONT;
}

/**
 * Editor options shared by the code view and the diff views. `fontFamily` is
 * read when the options are spread into an editor, so every editor and diff
 * opens in the Code font Settings chose.
 */
export const SHARED_EDITOR_OPTIONS = {
  fontSize: 12.5,
  lineHeight: 20,
  get fontFamily(): string {
    return codeFontFamily();
  },
  fontLigatures: false,
  minimap: { enabled: false },
  // A desktop pane, not a document: an editor that scrolls a screen past the
  // last line looks broken next to a tree that does not.
  scrollBeyondLastLine: false,
  smoothScrolling: true,
  renderLineHighlight: "line",
  renderWhitespace: "selection",
  guides: { indentation: true },
  padding: { top: 10, bottom: 24 },
  scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10, useShadows: false },
  overviewRulerBorder: false,
  automaticLayout: true,
  tabSize: 2,
  wordWrap: "off",
  stickyScroll: { enabled: false },
} as const satisfies editor.IStandaloneEditorConstructionOptions;
