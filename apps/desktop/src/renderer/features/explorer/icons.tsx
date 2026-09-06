/**
 * One icon per file type, for the tree and the tab strip.
 *
 * lucide only, and one weight: a tree whose rows carry six different icon
 * families reads as noise. What the icon has to do at 14px is separate a
 * config file from a script from a picture — not name the language, which the
 * filename beside it already does.
 */
import {
  Binary,
  Box,
  Braces,
  FileCode,
  FileImage,
  FileJson,
  FileText,
  FileType,
  Folder,
  FolderOpen,
  Hash,
  Settings2,
  SquareTerminal,
  Table,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { createElement } from "react";

const BY_EXTENSION: Record<string, LucideIcon> = {
  ts: FileCode,
  tsx: FileCode,
  mts: FileCode,
  cts: FileCode,
  js: FileCode,
  jsx: FileCode,
  mjs: FileCode,
  cjs: FileCode,
  py: FileCode,
  pyi: FileCode,
  rs: FileCode,
  go: FileCode,
  c: FileCode,
  h: FileCode,
  cc: FileCode,
  cpp: FileCode,
  hpp: FileCode,
  java: FileCode,
  rb: FileCode,
  php: FileCode,
  swift: FileCode,
  kt: FileCode,
  lua: FileCode,

  json: FileJson,
  jsonc: FileJson,
  json5: FileJson,
  ipynb: FileJson,

  yml: Settings2,
  yaml: Settings2,
  toml: Settings2,
  ini: Settings2,
  cfg: Settings2,
  conf: Settings2,
  env: Settings2,
  lock: Settings2,

  css: Braces,
  scss: Braces,
  sass: Braces,
  less: Braces,
  html: FileType,
  htm: FileType,
  xml: FileType,

  md: FileText,
  markdown: FileText,
  mdx: FileText,
  txt: FileText,
  log: FileText,

  csv: Table,
  tsv: Table,

  sh: SquareTerminal,
  bash: SquareTerminal,
  zsh: SquareTerminal,
  fish: SquareTerminal,

  png: FileImage,
  jpg: FileImage,
  jpeg: FileImage,
  gif: FileImage,
  webp: FileImage,
  svg: FileImage,
  bmp: FileImage,
  ico: FileImage,
  avif: FileImage,

  pdf: FileText,

  // The nine the CAD Viewer's surface renders get the one glyph that says so.
  step: Box,
  stp: Box,
  glb: Box,
  stl: Box,
  "3mf": Box,
  dxf: Box,
  urdf: Box,
  srdf: Box,
  sdf: Box,
};

/** Which lucide icon a path gets. Exported for the tests, not for rendering. */
export function fileIconFor(filePath: string): LucideIcon {
  const name = (filePath.split("/").pop() ?? filePath).toLowerCase();
  if (name.startsWith(".")) {
    return Hash;
  }
  const extension = name.includes(".") ? (name.split(".").pop() ?? "") : "";
  return BY_EXTENSION[extension] ?? (extension === "" ? FileText : Binary);
}

/**
 * The icons, as components rather than as values a caller renders.
 *
 * A caller that did `const Icon = fileIconFor(path)` and then `<Icon />` would
 * be selecting a component type during render — legal, but indistinguishable
 * from *defining* one there, which remounts the subtree on every render. These
 * two wrappers are module-level, so a row's icon is stable and the choice is
 * a `createElement` call rather than a JSX element type.
 */
export function FileIcon({ path, className }: { path: string; className?: string }) {
  return createElement(fileIconFor(path), { className, strokeWidth: 1.75 });
}

export function FolderIcon({ open, className }: { open: boolean; className?: string }) {
  return createElement(open ? FolderOpen : Folder, { className, strokeWidth: 1.75 });
}
