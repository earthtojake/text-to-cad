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
import { Code2, Eye, Palette, PanelRight } from "lucide-react";

import type { FileKind, FileStat } from "@shared/ipc/explorer";

import { CAD_PANEL, SOURCE_PANEL, type PanelsFor } from "./panels";

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
 * editor and the file sheet, which the viewer's surface draws into this
 * app's panel column and this app drives, because that surface's own top bar
 * — where its toggles live standalone — is hidden here. Code, images and
 * PDFs declare none, and a kind with none has the tree alone in the row.
 *
 * CAD files have an XML source too (`.urdf` and friends), and still no source
 * panel: the surface that renders them is a 3D scene, and a second editor
 * competing with it is not a second reading of the file.
 */
export type RendererTraits = {
  id: RendererId;
  /** The panels this kind has, in the order the nav row draws them. */
  panels: PanelsFor | null;
  /** True when the renderer writes back (the save path, the dirty dot). */
  editable: boolean;
};

/**
 * Markdown's one panel: the same bytes read as a document or as source.
 *
 * The one panel that is not a column — the source IS the body — and still
 * one of the list, so opening it closes the tree the way opening the tree
 * closes it. The label is what pressing it does.
 */
const markdownPanels: PanelsFor = ({ open }) => [
  {
    id: SOURCE_PANEL,
    label: open === SOURCE_PANEL ? "View preview" : "View source",
    icon: open === SOURCE_PANEL ? Eye : Code2,
    content: "body",
  },
];

/**
 * A CAD file's two: the viewer's theme editor and its file sheet, drawn by
 * the viewer's surface into the panel column this app owns (`panelSlot`).
 * The sheet is what a CAD tab opens with — a STEP file's tree and its
 * measurements are the reason the tab is open.
 *
 * Nothing until the surface is up: a CAD tab whose runtime did not start
 * shows a failure card, and two toggles over a card would open nothing.
 */
const cadPanels: PanelsFor = ({ ready }) =>
  ready
    ? [
        {
          id: CAD_PANEL.theme,
          label: "Theme settings",
          icon: Palette,
          content: "slot",
        },
        {
          id: CAD_PANEL.fileSheet,
          label: "File sheet",
          icon: PanelRight,
          content: "slot",
          defaultOpen: true,
        },
      ]
    : [];

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
