/**
 * Which renderer a file gets.
 *
 * One table, keyed by extension and mime, so the answer to "what will happen
 * when I open this" is in one place — and so the header knows whether to offer
 * `View source` before the content has loaded.
 *
 * Main answers the same question in `src/main/explorer/fs.ts` (`FileKind`),
 * for a different reason: it decides whether to send text or a data URL. The
 * two agree by construction — this table takes main's `FileKind` as its input
 * and only splits `text` further, into markdown and everything else.
 */
import type { FileKind, FileStat } from "@shared/ipc/explorer";

/** The renderers, in the order a reader should meet them. */
export type RendererId = "markdown" | "code" | "image" | "pdf" | "cad" | "binary";

/** The extensions the CAD Viewer's file surface understands (plan §3). */
export const CAD_EXTENSIONS = [
  "step",
  "stp",
  "glb",
  "stl",
  "3mf",
  "dxf",
  "urdf",
  "srdf",
  "sdf",
] as const;

const MARKDOWN_EXTENSIONS = new Set(["md", "markdown", "mdx"]);

/**
 * A renderer's traits, as the file tab's header needs them.
 *
 * `sourceToggle` is what puts `View source` in the header: markdown is the
 * only kind with two readings of the same bytes. CAD files have an XML source
 * too (`.urdf` and friends), but the surface that renders them is a 3D scene
 * with its own panels — a source toggle there would be a second editor
 * competing with it, and P4/P5 own that surface.
 */
export type RendererTraits = {
  id: RendererId;
  /** True when the renderer can be flipped to Monaco with `View source`. */
  sourceToggle: boolean;
  /** True when the renderer writes back (the save path, the dirty dot). */
  editable: boolean;
};

const TRAITS: Record<RendererId, RendererTraits> = {
  markdown: { id: "markdown", sourceToggle: true, editable: true },
  code: { id: "code", sourceToggle: false, editable: true },
  image: { id: "image", sourceToggle: false, editable: false },
  pdf: { id: "pdf", sourceToggle: false, editable: false },
  cad: { id: "cad", sourceToggle: false, editable: false },
  binary: { id: "binary", sourceToggle: false, editable: false },
};

/** Lowercase extension without the dot; `""` when there is none. */
export function extensionOf(filePath: string): string {
  const name = filePath.split("/").pop() ?? filePath;
  if (!name.includes(".") || name.startsWith(".")) {
    return "";
  }
  return (name.split(".").pop() ?? "").toLowerCase();
}

/** True when the path is one the CAD surface renders. */
export function isCadPath(filePath: string): boolean {
  return (CAD_EXTENSIONS as readonly string[]).includes(extensionOf(filePath));
}

/**
 * Pick a renderer from a path alone — what the header can know before the
 * file has been read.
 */
export function rendererForPath(filePath: string): RendererTraits {
  const extension = extensionOf(filePath);
  if (isCadPath(filePath)) {
    return TRAITS.cad;
  }
  if (MARKDOWN_EXTENSIONS.has(extension)) {
    return TRAITS.markdown;
  }
  return TRAITS.code;
}

/** Pick a renderer from main's answer, which is the one that decides. */
export function rendererFor(stat: FileStat): RendererTraits {
  const byKind: Record<FileKind, RendererId> = {
    text: MARKDOWN_EXTENSIONS.has(stat.extension) ? "markdown" : "code",
    image: "image",
    pdf: "pdf",
    cad: "cad",
    binary: "binary",
  };
  return TRAITS[byKind[stat.fileKind]];
}
