import { Box } from "lucide-react";

import { FileIcon } from "./icons.jsx";

/**
 * What a document is, as one small glyph, the same wherever the viewer lists documents (the
 * Home's cards and rows, the explorer's and the name menu's rows), 16px: a model, built from
 * code, is lucide's cube (`Box`); a CAD file lucide's plain `File`, whatever its kind (its name
 * says which).
 *
 * @param {{ model?: boolean, path: string, className?: string, strokeWidth?: number }} props
 */
/**
 * A document's glyph in a compact 24px row (the explorer's, the name menu's): 16px, as the Home's,
 * drawn 2px past each side of the trees' 12px glyph column, so the names start where they do.
 */
export const DOCUMENT_ROW_GLYPH_CLASS = "-mx-0.5 size-4 shrink-0 text-muted-foreground/70";

export function DocumentGlyph({ model = false, path, className, strokeWidth = 1.75 }) {
  return model
    ? <Box className={className} strokeWidth={strokeWidth} aria-hidden="true" data-glyph="model" />
    : <span className="contents" data-glyph="file"><FileIcon className={className} path={path} strokeWidth={strokeWidth} /></span>;
}
