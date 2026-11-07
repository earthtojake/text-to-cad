import { useI18n } from "@cad/ui/i18n";
import { useCallback, useMemo, useState } from "react";
import { TREE_ROW_NAME_CLASS, TreeRowGlyph, TreeRowLabel, TreeRowSurface, TreeRowToggle } from "@cad/ui/primitives/tree-row";
import { formatSheetSelector } from "@cad/core/lib/schematicRefs.js";
import { useFlatPanel } from "../kit/shell/FlatPanel.jsx";
import { buildSheetTree } from "./schematicTree.js";

function rowsOf(roots, collapsed) {
  const rows = [];
  const visit = (nodes, depth) => {
    for (const node of nodes) {
      const branch = node.children.length > 0, open = branch && !collapsed.has(node.id);
      rows.push({ node, depth, branch, open });
      if (open) visit(node.children, depth + 1);
    }
  };
  visit(roots, 0);
  return rows;
}

/**
 * A schematic's **Hierarchy**, a tab of the view's panel (`kit/shell/FlatPanel.jsx`), as KiCad's Hierarchy Navigator: the root
 * sheet, and under each sheet the sheets it places, in page order, each row its name and its page
 * number, the sheet shown lit. A press on a row shows that sheet; only a row's chevron opens or shuts
 * it, and every sheet starts open (a hierarchy is read whole). The pointer on a row lights its sheet's
 * symbol on the sheet shown, where it is placed. While the panel's search is up, the sheets whose
 * names or files match, as one list, and nothing when none does.
 *
 * @param {{ index: object, shown: string, onShow(path: string): void, onHover?(selector: string): void }} props
 */
export default function SheetsSection({ index, shown, onShow, onHover = () => {} }) {
  const { t } = useI18n();
  const tree = useMemo(() => buildSheetTree(index), [index]);
  const [collapsed, setCollapsed] = useState(() => new Set());
  const toggle = useCallback(id => setCollapsed(current => {
    const next = new Set(current);
    if (!next.delete(id)) next.add(id);
    return next;
  }), []);
  const rows = useMemo(() => rowsOf(tree.roots, collapsed), [tree, collapsed]);
  const panel = useFlatPanel();
  const query = panel?.query.trim().toLowerCase() ?? "";
  const show = path => { panel?.picked(); onShow(path); };
  const found = useMemo(() => {
    if (!query) return null;
    const hits = [];
    const visit = nodes => { for (const node of nodes) { if (`${node.label} ${node.file || ""}`.toLowerCase().includes(query)) hits.push(node); visit(node.children); } };
    visit(tree.roots);
    return hits;
  }, [tree, query]);
  const nameButton = (node, active) => <button type="button" aria-label={t("schematic.text.show_sheet", { name: node.label })} aria-current={active ? "page" : undefined}
    className={TREE_ROW_NAME_CLASS} onClick={() => show(node.path)} title={node.file}>
    <TreeRowLabel className="max-w-full shrink-0">{node.label}</TreeRowLabel>
    <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{node.detail}</TreeRowLabel>
  </button>;
  if (found) {
    return found.length ? <ul className="flex flex-col text-tiny" aria-label={t("schematic.text.schematic_sheets")} data-flat-panel-hit="">
      {found.map(node => <li key={node.id} className="min-w-0">
        <TreeRowSurface dense depth={0} active={node.path === shown} data-schematic-sheet-row={node.path}
          onMouseEnter={() => onHover(formatSheetSelector(node.path))} onMouseLeave={() => onHover("")}>
          <TreeRowGlyph />
          {nameButton(node, node.path === shown)}
        </TreeRowSurface>
      </li>)}
    </ul> : null;
  }
  return <ul className="flex flex-col py-1 text-tiny" role="tree" aria-label={t("schematic.text.schematic_sheets")}>
    {rows.map(({ node, depth, branch, open }) => {
      const active = node.path === shown;
      return <li key={node.id} role="treeitem" aria-level={depth + 1} aria-selected={active} aria-expanded={branch ? open : undefined} className="min-w-0">
        <TreeRowSurface dense depth={depth} active={active}
          data-schematic-sheet-row={node.path} onMouseEnter={() => onHover(formatSheetSelector(node.path))} onMouseLeave={() => onHover("")}>
          {branch ? <TreeRowToggle open={open} label={t(open ? "tree.collapse" : "tree.expand", { name: node.label })} onToggle={() => toggle(node.id)} />
            : <TreeRowGlyph />}
          {nameButton(node, active)}
        </TreeRowSurface>
      </li>;
    })}
  </ul>;
}
