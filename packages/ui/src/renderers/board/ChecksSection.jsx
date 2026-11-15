import { useI18n } from "@cad/ui/i18n";
import { useMemo, useState } from "react";
import { CircleAlert, CircleCheck, CircleDashed, CircleSlash, TriangleAlert } from "lucide-react";
import { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuSeparator, ContextMenuTrigger } from "@cad/ui/primitives/context-menu";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { TREE_GLYPH_STROKE, TREE_ROW_NAME_CLASS, TreeRowGlyph, TreeRowLabel, TreeRowSurface, useTreeRowHeight } from "@cad/ui/primitives/tree-row";
import { cn } from "@cad/ui/utils";
import VirtualRows from "../kit/inspector/VirtualRows.jsx";
import { useFlatPanel } from "../kit/shell/FlatPanel.jsx";
import { ViewMenuItems, menuEntry, menuGroups, referenceGroup } from "../kit/shell/viewMenu.js";

const GROUP_KEYS = { error: "board.checks.errors", warning: "board.checks.warnings", excluded: "board.checks.excluded" };
// A finding's glyph says how it counts: what fails the board, what does not, what the project excluded.
const GLYPHS = Object.freeze({ error: [CircleAlert, "text-destructive"], warning: [TriangleAlert, "text-amber-500"], excluded: [CircleSlash, "text-muted-foreground/70"] });
const additive = event => event.shiftKey || event.metaKey || event.ctrlKey;

/**
 * The verdict, in words a person with no electronics reads: "Design rule check: failed — 3 errors, 1
 * unrouted connection", "passed, 13 warnings", "not checked — <why>", "checking…".
 */
export function checksVerdict(checks, t) {
  const count = (n, one, many) => t(n === 1 ? one : many, { count: n });
  if (checks.state === "checking") return t("board.checks.checking");
  if (checks.state === "notChecked") return checks.reason ? t("board.checks.not_checked_reason", { reason: checks.reason }) : t("board.checks.not_checked");
  const { errors, unconnected, warnings } = checks.counts;
  if (checks.verdict === "pass") {
    return warnings ? t("board.checks.passed_warnings", { warnings: count(warnings, "board.checks.count_warning", "board.checks.count_warnings") }) : t("board.checks.passed");
  }
  const said = [errors ? count(errors, "board.checks.count_error", "board.checks.count_errors") : "",
    unconnected ? count(unconnected, "board.checks.count_unrouted", "board.checks.count_unrouted_many") : ""].filter(Boolean);
  if (said.length === 2) return t("board.checks.failed_two", { errors: said[0], unrouted: said[1] });
  return said.length ? t("board.checks.failed_one", { problems: said[0] }) : checks.reason ? t("board.checks.failed_one", { problems: checks.reason }) : t("board.checks.failed");
}

/** A finding's row menu, built as it opens: its reference in words, Select or Deselect, and its framing. */
function RowMenu({ entriesOf, children }) {
  const [open, setOpen] = useState(false);
  return <ContextMenu onOpenChange={setOpen}><ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
    <ContextMenuContent className="w-44">
      {open ? <ViewMenuItems entries={entriesOf()} Item={ContextMenuItem} Separator={ContextMenuSeparator} /> : null}
    </ContextMenuContent>
  </ContextMenu>;
}

// One finding: its glyph, KiCad's description of it and, in the room it leaves, KiCad's rule name, muted, as a
// row of the Parts is its name then its detail; the whole description is its hint where the row clips it. A
// press selects what it is between, a double-click frames it.
function CheckRow({ finding, lit, choose, frame, hover, menu }) {
  const { t } = useI18n();
  const [Glyph, tone] = GLYPHS[finding.group];
  const name = <>
    <TreeRowLabel className="max-w-full shrink-0">{finding.description}</TreeRowLabel>
    {finding.type ? <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{finding.type}</TreeRowLabel> : null}
  </>;
  const whole = [finding.description, finding.comment].filter(Boolean).join(" — ");
  return <RowMenu entriesOf={() => menu(finding)}>
    <TreeRowSurface dense depth={0} active={lit} className="group/row" data-board-check={finding.id} data-check-group={finding.group}
      onMouseEnter={() => hover(finding.picks[0] || "")} onMouseLeave={() => hover("")}>
      <TreeRowGlyph><Glyph className={cn("size-3 shrink-0", tone)} strokeWidth={TREE_GLYPH_STROKE} /></TreeRowGlyph>
      <TooltipHint content={whole} side="right" overflowOnly>
        {finding.picks.length ? <button type="button" aria-label={t("tree.select", { name: finding.description })} aria-pressed={lit}
          onClick={event => choose(finding, event)} onDoubleClick={() => frame(finding)} className={TREE_ROW_NAME_CLASS}>{name}</button>
          : <span className={cn(TREE_ROW_NAME_CLASS, "cursor-default")} onDoubleClick={() => frame(finding)}>{name}</span>}
      </TooltipHint>
    </TreeRowSurface>
  </RowMenu>;
}

/**
 * A board's **Checks**, a tab of the view's panel (`kit/shell/FlatPanel.jsx`): KiCad's design rule check
 * of the saved board (`useBoardChecks.js`), read-only as everything here is. First the verdict, in plain
 * words; then what the check said beside its findings (no project or no schematic beside the board), muted;
 * then the findings, a row each (the panel's one row), under what they are: **Errors** (what fails the
 * board: an error, a missing connection, a difference from the schematic), **Warnings**, then **Excluded**
 * (what the board's project excludes, which fails nothing). A press on a row selects what the finding is
 * between, as a press on the picture does (Shift, Ctrl or Cmd adds; a press on the lit row lets go), so
 * Quick Edit and Copy Reference carry those references; a double-click frames the finding where it is
 * (`onFrame`, its `box`); a finding KiCad gave no item and no place is listed and does neither. Its row
 * menu: Copy Reference (the finding as `cad kicad_pcb drc` says it, then its items' references), Select or
 * Deselect, Zoom to it. While the panel's search is up, the findings that match, flat, and nothing else.
 *
 * @param {{ checks: NonNullable<ReturnType<typeof import("./useBoardChecks.js").useBoardChecks>>,
 *   selection: ReturnType<typeof import("../kit/tools/select/useSceneSelection.js").useSceneSelection>,
 *   held: string, onHold(id: string): void, onSelect(): void, onFrame(box: readonly number[]): void,
 *   copyOf(finding: object): string, onCopy: ((text: string) => void) | null }} props
 *   `held`: the finding whose row was pressed last, lit while everything it picked is still selected.
 */
export default function ChecksSection({ checks, selection, held, onHold, onSelect, onFrame, copyOf, onCopy }) {
  const { t } = useI18n();
  const rowHeight = useTreeRowHeight();
  const flatPanel = useFlatPanel();
  const query = flatPanel?.query.trim().toLowerCase() ?? "";
  const { selected, select, clear, hover } = selection;
  const picked = useMemo(() => new Set(selected), [selected]);
  const litId = useMemo(() => {
    const finding = checks.findings.find(candidate => candidate.id === held);
    return finding?.picks.length && finding.picks.every(id => picked.has(id)) ? finding.id : "";
  }, [checks, held, picked]);
  const rows = useMemo(() => {
    if (query) {
      return checks.findings.filter(finding => [finding.description, finding.type, finding.comment, ...finding.items.flatMap(item => [item.description, item.selector])]
        .some(text => text && text.toLowerCase().includes(query))).map(finding => ({ key: finding.id, finding }));
    }
    return Object.keys(GROUP_KEYS).flatMap(group => {
      const findings = checks.findings.filter(finding => finding.group === group);
      return findings.length ? [{ key: `group:${group}`, group, count: findings.length }, ...findings.map(finding => ({ key: finding.id, finding }))] : [];
    });
  }, [checks, query]);

  const choose = (finding, event) => {
    flatPanel?.picked?.();
    onSelect?.();
    const add = additive(event);
    // A press on the lit row lets go of it, as a second press on a selected part does.
    if (!add && litId === finding.id) { clear(); onHold(""); return; }
    if (!add) clear();
    for (const id of finding.picks) if (!add || !picked.has(id)) select(id, { multiSelect: true });
    onHold(finding.id);
  };
  const frame = finding => { if (finding.box) onFrame(finding.box); };
  const menu = finding => {
    const text = copyOf(finding), lit = litId === finding.id;
    return menuGroups(
      onCopy ? referenceGroup({ copyText: text, onCopy: () => onCopy(text), t }) : [],
      finding.picks.length ? [menuEntry("select", lit ? t("menu.deselect") : t("tool.select"), { onSelect: () => choose(finding, {}) })] : [],
      finding.box ? [menuEntry("zoom-to", t("menu.zoomToNamed", { name: finding.description }), { onSelect: () => frame(finding) })] : []);
  };
  const renderRow = at => {
    const row = rows[at];
    if (row.group) {
      return <div className="flex items-center gap-1 px-2 text-muted-foreground" style={{ height: rowHeight }} data-check-heading={row.group}>
        <span>{t(GROUP_KEYS[row.group])}</span><span className="text-micro tabular-nums">{row.count.toLocaleString("en-US")}</span>
      </div>;
    }
    return <CheckRow finding={row.finding} lit={litId === row.finding.id} choose={choose} frame={frame} hover={hover} menu={menu} />;
  };
  const list = rows.length ? <VirtualRows key={query ? "search" : "list"} aria-label={t("board.checks.list")} count={rows.length} rowHeight={rowHeight}
    rowKey={at => rows[at].key} rowProps={() => ({ className: "min-w-0" })} renderRow={renderRow} /> : null;
  // Searching: the findings that match, as one list; none, nothing (the panel leaves the tab out).
  if (query) return list ? <div className="text-tiny" data-board-checks="" data-flat-panel-hit="">{list}</div> : null;
  const failed = checks.verdict === "fail", passed = checks.verdict === "pass";
  const Verdict = failed ? CircleAlert : passed ? CircleCheck : CircleDashed;
  return <div className="flex flex-col pt-1 text-tiny" data-board-checks="" data-checks-state={checks.verdict || checks.state}>
    <p role="status" className="flex items-start gap-1 px-2 py-1 leading-4 text-foreground" data-checks-verdict="">
      <Verdict className={cn("mt-0.5 size-3 shrink-0", failed ? "text-destructive" : passed ? "text-emerald-500 dark:text-emerald-400" : "text-muted-foreground")}
        strokeWidth={TREE_GLYPH_STROKE} aria-hidden="true" />
      <span className="min-w-0 break-words">{checksVerdict(checks, t)}</span>
    </p>
    {checks.notes.map(note => <p key={`${note.code}:${note.message}`} className="px-2 pb-1 pl-6 text-micro leading-4 text-muted-foreground break-words" data-checks-note={note.code}>{note.message}</p>)}
    {list}
  </div>;
}
