/**
 * Which renderer a file gets, and which panels it has.
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
import { cadPanels as cadSurfacePanels, markdownPanels as markdownSourcePanel, type FilePanel } from "cad-viewer/shell";

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
 * `panels` is what puts toggles in the nav row (`panels.ts`): markdown has
 * one, the two readings of the same bytes; a CAD file has two, the theme
 * editor and the Inspector, which the viewer's surface draws into this
 * app's panel column and this app drives, because that surface's own top bar
 * — where its toggles live standalone — is hidden here. Code, images and
 * PDFs declare none, and a kind with none has the tree alone in the row.
 *
 * CAD files have an XML source too (`.urdf` and friends), and still no source
 * panel: the surface that renders them is a 3D scene, and a second editor
 * competing with it is not a second reading of the file.
 */
export type PanelsFor = (context: { open: string; ready: boolean }) => FilePanel[];

export type RendererTraits = {
  id: RendererId;
  /** The panels this kind has, in the order the nav row draws them. */
  panels: PanelsFor | null;
  /** True when the renderer writes back (the save path, the dirty dot). */
  editable: boolean;
};

/**
 * Markdown's one panel and the CAD surface's two, both declared in the shared
 * shell (`cad-viewer/shell`'s `panels.js`) and named here.
 *
 * The CAD pair is shared because BOTH apps draw it: the standalone viewer's
 * nav row has the same two toggles over the same two panels, with the same
 * labels, glyphs and default. Declaring them twice is how one of them would
 * come to say "File sheet" while the other says "Inspector".
 */
const markdownPanels: PanelsFor = ({ open }) => markdownSourcePanel(open);
const cadPanels: PanelsFor = ({ ready }) => cadSurfacePanels(ready);

const TRAITS: Record<RendererId, RendererTraits> = {
  markdown: { id: "markdown", panels: markdownPanels, editable: true },
  code: { id: "code", panels: null, editable: true },
  image: { id: "image", panels: null, editable: false },
  pdf: { id: "pdf", panels: null, editable: false },
  cad: { id: "cad", panels: cadPanels, editable: false },
  binary: { id: "binary", panels: null, editable: false },
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
