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
// The explorer registers every theme, the transcript's transparent variants
// included (`setupMonaco`), so there is one place and one order for them.
import { languageFor, setupMonaco } from "@renderer/features/explorer/renderers/code/editor";

export function configureMonaco(): typeof monaco {
  setupMonaco();
  return monaco;
}

/** Monaco's language id for a path, by extension; plain text otherwise. */
export function languageForPath(file: string): string {
  return languageFor(file);
}
