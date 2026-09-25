/**
 * One icon per file type, for a file tree, a breadcrumb menu and a tab strip.
 *
 * lucide only, and one weight: a tree whose rows carry six different icon
 * families reads as noise. What the icon has to do at 14px is separate a
 * config file from a script from a picture — not name the language, which the
 * filename beside it already does.
 *
 * The nine formats the CAD Viewer renders are the exception, and they are not
 * an exception to that rule: they go through the viewer's own `EntryIcon`, so
 * a `.stl` is the triangle it is made of and a `.step` is a solid cube,
 * everywhere either app lists files. `cadgen-js`'s `fileFormats` decides
 * which nine those are — one authority, reachable from both apps.
 */
import {
  Binary,
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
  Table
} from "lucide-react";
import { createElement } from "react";
import { renderFormatFromPath } from "cadgen-js/lib/fileFormats.js";

import EntryIcon from "@/components/workbench/EntryIcon";

const BY_EXTENSION = {
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

  pdf: FileText
};

/**
 * Which lucide icon a NON-CAD path gets. Exported for the tests, not for
 * rendering — a CAD path never reaches this table.
 *
 * @param {string} filePath
 */
export function fileIconFor(filePath) {
  const name = (String(filePath || "").split("/").pop() ?? filePath).toLowerCase();
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
 *
 * @param {{ path: string, className?: string }} props
 */
export function FileIcon({ path, className }) {
  const renderFormat = renderFormatFromPath(path);
  if (renderFormat) {
    // A file the CAD Viewer renders: its own per-format glyph, from the one
    // table every surface that lists files already reads.
    return (
      <EntryIcon
        entry={{ file: path, kind: renderFormat }}
        sourceFormat={renderFormat}
        className={className}
        strokeWidth={1.75}
      />
    );
  }
  return createElement(fileIconFor(path), { className, strokeWidth: 1.75 });
}

/**
 * @param {{ open: boolean, className?: string }} props
 */
export function FolderIcon({ open, className }) {
  return createElement(open ? FolderOpen : Folder, { className, strokeWidth: 1.75 });
}
