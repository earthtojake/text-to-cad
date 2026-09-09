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
import * as monaco from "monaco-editor";
// The explorer owns the worker environment and the base themes; the session
// only adds two transparent variants so a diff sits on the transcript itself.
import { languageFor, setupMonaco } from "@hardcore/ui/renderers/code/editor";

let configured = false;

export function configureMonaco(): typeof monaco {
  if (!configured) {
    configured = true;
    setupMonaco();
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
  return languageFor(file);
}
