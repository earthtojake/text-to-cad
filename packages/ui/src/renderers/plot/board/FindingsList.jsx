import { memo, useMemo } from "react";
import { parseBoardRefSelector } from "@text-to-cad/core/lib/boardRefs.js";
import { cn } from "@text-to-cad/ui/utils";
import ToolPanel from "../../kit/tools/ToolPanel.jsx";
import { moreThan } from "./boardFacts.js";
import { naturalCompare } from "./boardTree.js";

/**
 * What KiCad and the review found on a board or a schematic, each in KiCad's order: what stops an
 * order (the errors) in the alert card, over the picture until it is put away, as a 3D view's alerts
 * are; the rest (the suggestions) in Select's folded Checks panel, read only by a person who opens it.
 * Choosing one hands it to `onChoose`.
 */

const sentence = (finding) => finding.summary || finding.description;

/** A board's findings as the card and Checks take them: the errors, which stop an order, and the rest. */
export function splitFindings(findings) {
  const errors = [], suggestions = [];
  for (const finding of findings || []) (finding.severity === "error" ? errors : suggestions).push(finding);
  return { errors, suggestions };
}

/**
 * The card's alert while there are errors, "1 to fix" (`usePlaneShell`'s `reportAlert`). Its key is
 * their sentences, so a rebuild that changes them is a new alert.
 *
 * @param {readonly object[]} errors
 * @returns {object | null}
 */
export function findingsAlert(errors) {
  if (!errors.length) return null;
  return { severity: "error", blocking: false, report: false, title: `${errors.length} to fix`, message: "",
    key: JSON.stringify(errors.map(sentence)) };
}

const ROW_CLASS = "w-full text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** The card's body: what to fix before ordering, each its sentence in full. */
export default function FindingsList({ errors, onChoose }) {
  return <section className="min-w-0" data-findings="">
    <h3 className="mb-1 text-xs font-normal leading-4 text-muted-foreground">Fix before ordering</h3>
    <ul className="-mx-2 flex min-w-0 flex-col">
      {errors.map((finding) => <li key={finding.index} className="min-w-0">
        <button type="button" onClick={() => onChoose(finding)} data-finding-row={finding.index}
          className={cn(ROW_CLASS, "rounded-md px-2 py-1 text-sm leading-5 text-foreground break-words whitespace-normal")}>
          {sentence(finding)}
        </button>
      </li>)}
    </ul>
  </section>;
}

const SHOWN_NAMES = 4;

/** What a reference reads as in a list: `#U3.9` is U3, `#net:VIN` is VIN. */
function refName(selector) {
  const parsed = parseBoardRefSelector(selector);
  return parsed?.ref || parsed?.net || null;
}

/**
 * The suggestions grouped by kind (their check and type), in the order each first appears: KiCad
 * reports a silkscreen clearance once per pair, so a board says it twenty times. A group reads as
 * its findings' one sentence, else what every finding of its type is called (the plot's `title`);
 * under it, what it is about (its parts and nets, once each). It is chosen as one finding whose
 * items are all of its findings'.
 */
function groupFindings(findings) {
  const groups = new Map();
  for (const finding of findings) {
    const kind = `${finding.check}:${finding.type}`;
    if (!groups.has(kind)) groups.set(kind, []);
    groups.get(kind).push(finding);
  }
  return [...groups].map(([kind, members]) => {
    const sentences = new Set(members.map(sentence));
    const names = [...new Set(members.flatMap((finding) => finding.items.map((item) => item.ref && refName(item.ref)).filter(Boolean)))].sort(naturalCompare);
    const more = moreThan(names.length, SHOWN_NAMES);
    return {
      kind, count: members.length,
      heading: sentences.size === 1 ? [...sentences][0] : members[0].title || members[0].description,
      names: [names.slice(0, SHOWN_NAMES).join(", "), more].filter(Boolean).join(" "),
      chosen: { ...members[0], items: members.flatMap((finding) => finding.items) },
    };
  });
}

/** Select's Checks panel: the suggestions, folded until a person opens it, one row per kind of finding. */
export const ChecksPanel = memo(function ChecksPanel({ suggestions, onChoose, active }) {
  const groups = useMemo(() => groupFindings(suggestions), [suggestions]);
  if (!groups.length) return null;
  return <ToolPanel id="checks" title="Checks" label="Checks" defaultCollapsed hidden={!active}>
    <ul className="flex min-w-0 flex-col px-1 pb-1 text-tiny" data-checks="">
      {groups.map((group) => <li key={group.kind} className="min-w-0">
        <button type="button" onClick={() => onChoose(group.chosen)} data-finding-row={group.chosen.index} aria-label={group.heading}
          className={cn(ROW_CLASS, "flex min-w-0 flex-col rounded-sm px-2 py-1")}>
          <span className="flex w-full min-w-0 items-baseline gap-1.5">
            <span className="min-w-0 flex-1 break-words text-foreground">{group.heading}</span>
            {group.count > 1 ? <span className="shrink-0 tabular-nums text-muted-foreground">{group.count}</span> : null}
          </span>
          {group.names ? <span className="min-w-0 truncate text-micro text-muted-foreground">{group.names}</span> : null}
        </button>
      </li>)}
    </ul>
  </ToolPanel>;
});
