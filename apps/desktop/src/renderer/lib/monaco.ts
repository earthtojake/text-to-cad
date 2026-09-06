/**
 * Monaco, self-hosted.
 *
 * `@monaco-editor/react` loads the editor from a CDN by default; this app
 * runs offline, behind a CSP with `script-src 'self'`, so the package is
 * pointed at the bundled `monaco-editor` and the worker comes from Vite as
 * a separate chunk (`?worker`, never `?worker&inline`: an inline worker is
 * a blob URL and the CSP refuses it).
 *
 * Imported lazily by the diff view, so a transcript with no diffs never
 * pays for the editor.
 */
import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
// monaco-editor's exports map rewrites `./*` to `./esm/vs/*.js`, so the
// worker is addressed without the `esm/vs` prefix.
import EditorWorker from "monaco-editor/editor/editor.worker?worker";

declare global {
  interface Window {
    MonacoEnvironment?: { getWorker: (workerId: string, label: string) => Worker };
  }
}

let configured = false;

export function configureMonaco(): typeof monaco {
  if (!configured) {
    configured = true;
    window.MonacoEnvironment = { getWorker: () => new EditorWorker() };
    loader.config({ monaco });
    // The stock themes, with the editor's own background removed so the
    // diff sits on the transcript's surface instead of a second one.
    monaco.editor.defineTheme("hardcore-light", {
      base: "vs",
      inherit: true,
      rules: [],
      colors: { "editor.background": "#00000000", "editorGutter.background": "#00000000" },
    });
    monaco.editor.defineTheme("hardcore-dark", {
      base: "vs-dark",
      inherit: true,
      rules: [],
      colors: { "editor.background": "#00000000", "editorGutter.background": "#00000000" },
    });
  }
  return monaco;
}

/** Monaco's language id for a path, by extension; plain text otherwise. */
export function languageForPath(file: string): string {
  const ext = file.split(".").pop()?.toLowerCase() ?? "";
  const known: Record<string, string> = {
    ts: "typescript",
    tsx: "typescript",
    mts: "typescript",
    js: "javascript",
    jsx: "javascript",
    mjs: "javascript",
    cjs: "javascript",
    py: "python",
    json: "json",
    md: "markdown",
    css: "css",
    html: "html",
    yml: "yaml",
    yaml: "yaml",
    toml: "ini",
    sh: "shell",
    bash: "shell",
    zsh: "shell",
    rs: "rust",
    go: "go",
    c: "c",
    h: "c",
    cpp: "cpp",
    hpp: "cpp",
    java: "java",
    xml: "xml",
    urdf: "xml",
    sdf: "xml",
    srdf: "xml",
    sql: "sql",
  };
  return known[ext] ?? "plaintext";
}
