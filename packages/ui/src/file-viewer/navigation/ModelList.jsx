import { LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { TreeFilterInput } from "@text-to-cad/ui/primitives/tree-filter";
import { TREE_GLYPH_STROKE, TREE_ROW_INSET_PX, TreeRowLabel, TreeRowSurface } from "@text-to-cad/ui/primitives/tree-row";
import { useI18n } from "@text-to-cad/ui/i18n";
import { ageLabel, lastActivity } from "../../lib/age.js";
import { DOCUMENT_ROW_GLYPH_CLASS, DocumentGlyph } from "./DocumentGlyph.jsx";
import { useControlUsage } from "../../usage/controls.js";

/** The most the Models tab lists: the Home, one click away, has the rest. */
export const MODEL_ROWS = 8;

/** Whether a library row is a document built from code (a model's, a shape's), not a file. */
const built = row => row.kind === "model" || row.kind === "shape";

/**
 * The Models tab's rows: the library's models alone (no file) whose name holds every word of
 * `query`, by last activity (the later of when each was opened and updated), newest first, at most
 * `MODEL_ROWS`.
 *
 * @template {{ path: string, name?: string, kind?: string, opened?: number | null, updated?: number | null }} Row
 * @param {readonly Row[]} rows
 * @param {string} [query]
 * @returns {Row[]}
 */
export function modelRows(rows, query = "") {
  const words = String(query).trim().toLowerCase().split(/\s+/).filter(Boolean);
  const named = row => words.every(word => String(row.name ?? "").toLowerCase().includes(word));
  return rows.map((row, index) => ({ row, index, at: lastActivity(row) ?? 0 })).filter(({ row }) => built(row) && named(row))
    .sort((a, b) => b.at - a.at || a.index - b.index).slice(0, MODEL_ROWS).map(({ row }) => row);
}

function Note({ children, busy = false }) {
  return <p className="px-3 py-4 text-center text-xs text-muted-foreground" role={busy ? "status" : undefined}>
    {busy ? <LoaderCircle className="mr-1.5 inline size-3 animate-spin align-[-2px]" aria-hidden="true" /> : null}{children}
  </p>;
}

/**
 * The name menu's Models tab, in the explorer's own style (`FolderExplorer`): one compact row per
 * model -- its glyph, its name, and at the right how long ago it was last active, with no verb --
 * the one on screen highlighted, under "Filter models...", as the Files tab is under "Filter
 * files...". Read from the host's library once per opening. A press
 * opens a document (`onOpen`, as the explorer's does); Up and Down move between the rows.
 *
 * @param {{ recent: { list(): Promise<readonly { path: string, name: string, kind?: string, opened?: number | null, updated?: number | null, missing?: boolean }[]> },
 *   current: string, onOpen(path: string): void }} props
 */
export function ModelList({ recent, current, onOpen }) {
  const { t, locale } = useI18n();
  const [listed, setListed] = useState({ rows: null, error: null });
  const [query, setQueryState] = useState("");
  // A filter begun is a use (`usage/controls.js`); never what it looks for.
  const usage = useControlUsage();
  const setQuery = next => { if (!query.trim() && String(next).trim()) usage.used("models_filter"); setQueryState(next); };
  const rows = useRef(null);
  useEffect(() => {
    let active = true;
    recent.list().then(
      found => { if (active) setListed({ rows: found, error: null }); },
      error => { if (active) setListed({ rows: null, error }); },
    );
    return () => { active = false; };
  }, [recent]);
  // Up and Down walk the filter and the rows: Down from the filter into the first, Up from the first
  // back to it.
  const walk = event => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const list = rows.current?.closest("[data-model-list]");
    const all = [...(list?.querySelectorAll("[data-model-row]:not(:disabled)") ?? [])];
    const at = all.indexOf(event.target.closest?.("[data-model-row]"));
    const next = event.key === "ArrowDown" ? all[at + 1] : at > 0 ? all[at - 1] : at === 0 ? list?.querySelector("input") : null;
    event.preventDefault();
    next?.focus();
  };
  const shown = listed.rows ? modelRows(listed.rows, query) : null;
  const now = Date.now();
  let body;
  if (listed.error) body = <Note>{t("explorer.modelsFailed")}</Note>;
  else if (!shown) body = <Note busy>{t("explorer.loading")}</Note>;
  else if (!shown.length) body = <Note>{query.trim() && modelRows(listed.rows).length ? t("explorer.noModelsMatch") : t("explorer.noModels")}</Note>;
  else body = shown.map(row => <TooltipHint key={row.path} content={row.name} overflowOnly>
    <TreeRowSurface as="button" type="button" active={row.path === current} className="disabled:opacity-50"
      style={{ paddingLeft: TREE_ROW_INSET_PX }} data-model-row="" data-path={row.path} disabled={row.missing}
      aria-current={row.path === current ? "true" : undefined} onClick={() => onOpen(row.path)}>
      <DocumentGlyph model={built(row)} path={row.path} className={DOCUMENT_ROW_GLYPH_CLASS} strokeWidth={TREE_GLYPH_STROKE} />
      <TreeRowLabel className="flex-1">{row.name}</TreeRowLabel>
      <span className="ml-2 shrink-0 text-muted-foreground" data-model-age="">{ageLabel(lastActivity(row), now, t, locale)}</span>
    </TreeRowSurface>
  </TooltipHint>);
  return <div className="flex min-h-0 flex-1 flex-col" data-model-list="">
    <TreeFilterInput label={t("explorer.filterModelsLabel")} placeholder={t("explorer.filterModelsPlaceholder")} value={query} onChange={setQuery} onKeyDown={walk} />
    <ScrollArea className="min-h-0 flex-1" viewportClassName="p-1" viewportRef={rows} viewportProps={{ onKeyDown: walk }}>
      {body}
    </ScrollArea>
  </div>;
}
