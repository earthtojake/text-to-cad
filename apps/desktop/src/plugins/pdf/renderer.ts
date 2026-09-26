import { performPdfCommand } from "@renderer/state/live-documents";

import type { RendererPlugin } from "../renderer";
import manifest from "./manifest.mjs";
import { pdfRenderer } from "./viewer";

/**
 * PDF's viewer binds its live document through the host's `pdf` port (`@hardcore/ui/host`), which
 * the app's live-document store keeps per tab; its commands are answered from there.
 */
const pdf: RendererPlugin = {
  manifest,
  renderers: () => [pdfRenderer],
  perform: (kind, params, scope) => performPdfCommand(kind, params, scope),
};
export default pdf;
