import { Folder } from "lucide-react";
import { useRef } from "react";

import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { TREE_GLYPH_STROKE, TREE_ROW_DENSE_ICON_CLASS, TREE_ROW_NAME_CLASS, TreeRowGlyph, TreeRowHeading, TreeRowLabel, TreeRowSurface } from "@cad/ui/primitives/tree-row";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";

import { DocumentGlyph } from "./DocumentGlyph.jsx";
import { useControlUsage } from "../../usage/controls.js";

/** Whether a row is a document built from code (a model's, a shape's), not a file. */
const built = row => row.kind === "model" || row.kind === "shape";

/** `path` as the list compares and groups it: forward slashes, no trailing one. */
const slashed = path => String(path || "").replace(/\\/g, "/").replace(/\/+$/, "");

/**
 * A project's documents as the list shows them: its models, then its files in groups by their folder below the
 * project's (`""`: its own), each group in the order the host gave (the server's: by folder, then by name).
 *
 * @template {{ path: string, kind?: string, folder?: string }} Row
 * @param {readonly Row[]} documents
 * @param {string} root
 * @returns {{ models: Row[], folders: { folder: string, rows: Row[] }[] }}
 */
export function projectGroups(documents, root) {
  const base = slashed(root);
  const models = documents.filter(built);
  const folders = [];
  for (const row of documents) {
    if (built(row)) continue;
    const folder = slashed(row.folder ?? row.path.slice(0, row.path.lastIndexOf("/")));
    const below = folder === base ? "" : folder.startsWith(`${base}/`) ? folder.slice(base.length + 1) : folder;
    const group = folders.find(entry => entry.folder === below);
    if (group) group.rows.push(row);
    else folders.push({ folder: below, rows: [row] });
  }
  return { models, folders };
}

/**
 * The Project tab: every document of the project the view's document is in, one click from each other (Fusion's Data
 * Panel, VS Code's Explorer, KiCad's project tree) -- its models under Models, then its CAD files under Files, the
 * project folder's own first and then each folder's under its path below the project's, each a dense panel row of its
 * glyph and name, the one on screen marked. A press opens a document (`onOpen`); Up and Down move between the rows.
 * Nothing above the project is listed, and there is no search: a project is a handful of rows (the server's walk is
 * bounded, and says when it stopped early, `truncated`).
 *
 * @param {{ project: { root: string, documents: readonly { path: string, name: string, kind?: string, folder?: string, missing?: boolean }[] | null,
 *   truncated?: boolean, missing?: boolean, error?: string | null }, current: string, onOpen(row: object): void }} props
 */
export function ProjectList({ project, current, onOpen }) {
  const { t } = useI18n();
  const usage = useControlUsage();
  const list = useRef(null);
  const here = slashed(current);
  // Up and Down walk the rows, as a tree's arrows do.
  const walk = event => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const rows = [...(list.current?.querySelectorAll("[data-project-row]:not(:disabled)") ?? [])];
    const at = rows.indexOf(event.target.closest?.("[data-project-row]"));
    const next = rows[event.key === "ArrowDown" ? at + 1 : at - 1];
    if (!next) return;
    event.preventDefault();
    next.focus();
  };
  if (project.error) return <Note>{t("project.readFailed")}</Note>;
  if (project.missing) return <Note>{t("project.folderMissing")}</Note>;
  if (!project.documents) return <Note busy>{t("project.loading")}</Note>;
  if (!project.documents.length) return <Note>{t("project.empty")}</Note>;
  const { models, folders } = projectGroups(project.documents, project.root);
  const row = (entry, depth) => {
    const active = slashed(entry.path) === here;
    return <li key={entry.path} className="min-w-0">
      <TooltipHint content={entry.name} overflowOnly>
        <TreeRowSurface as="button" type="button" dense depth={depth} active={active} disabled={entry.missing} className="disabled:opacity-50"
          aria-current={active ? "page" : undefined} data-project-row="" data-path={entry.path}
          onClick={() => { if (active) return; usage.used("project_open"); onOpen(entry); }}>
          <TreeRowGlyph><DocumentGlyph model={built(entry)} path={entry.path} className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} /></TreeRowGlyph>
          <span className={cn(TREE_ROW_NAME_CLASS, "pointer-events-none")}><TreeRowLabel>{entry.name}</TreeRowLabel></span>
        </TreeRowSurface>
      </TooltipHint>
    </li>;
  };
  return <div ref={list} className="flex flex-col" onKeyDown={walk} data-project-list="">
    {models.length ? <ul aria-label={t("project.models")} data-project-group="models">
      <TreeRowHeading as="li" aria-hidden="true">{t("project.models")}</TreeRowHeading>
      {models.map(entry => row(entry, 0))}
    </ul> : null}
    {folders.length ? <ul aria-label={t("project.files")} data-project-group="files">
      <TreeRowHeading as="li" aria-hidden="true">{t("project.files")}</TreeRowHeading>
      {folders.map(group => [
        group.folder ? <li key={`folder:${group.folder}`} className="min-w-0" aria-hidden="true">
          <TreeRowSurface dense depth={0} className="text-muted-foreground" data-project-folder={group.folder}>
            <TreeRowGlyph><Folder className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} /></TreeRowGlyph>
            <span className={TREE_ROW_NAME_CLASS}><TreeRowLabel>{group.folder}</TreeRowLabel></span>
          </TreeRowSurface>
        </li> : null,
        ...group.rows.map(entry => row(entry, group.folder ? 1 : 0)),
      ])}
    </ul> : null}
    {project.truncated ? <p className="px-1 py-2 text-xs text-muted-foreground" data-project-truncated="">{t("project.truncated")}</p> : null}
  </div>;
}

function Note({ children, busy = false }) {
  return <p className="px-1 py-4 text-center text-xs text-muted-foreground" role={busy ? "status" : undefined}>{children}</p>;
}
