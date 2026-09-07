/**
 * What the editors need to know, with nothing loaded to know it.
 *
 * Split from `monaco-setup.ts` on purpose: that module imports the whole of
 * `monaco-editor` and its five workers for their side effects, and this one is
 * a lookup table and an options object. Anything that only wants "what
 * language is this file" — the file tab's header, a test — should not pull two
 * megabytes of editor in to find out.
 */
import type { editor } from "monaco-editor";

export const MONACO_LIGHT = "hardcore-light";
export const MONACO_DARK = "hardcore-dark";

export function monacoTheme(resolved: "light" | "dark"): string {
  return resolved === "dark" ? MONACO_DARK : MONACO_LIGHT;
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

/** Editor options shared by the code view and the diff views. */
export const SHARED_EDITOR_OPTIONS = {
  fontSize: 12.5,
  lineHeight: 20,
  fontFamily:
    'ui-monospace, "SF Mono", SFMono-Regular, Menlo, Monaco, "Cascadia Mono", Consolas, monospace',
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
