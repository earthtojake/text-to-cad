import { useMemo } from "react";
import { cn } from "@text-to-cad/ui/utils";
import ToolPanel from "../../kit/tools/ToolPanel.jsx";

/**
 * What KiCad and the review found on a board or a schematic, each in KiCad's order, each its
 * sentence in full: what stops an order (the errors) in the alert card, over the picture until it
 * is put away, as a 3D view's alerts are; the rest (the suggestions) in Select's folded Checks
 * panel, read only by a person who opens it. Choosing one hands it to `onChoose`.
 */

/** Whether a finding stops an order: an error, whichever check found it. */
export const findingBlocks = (finding) => finding.severity === "error";

/**
 * What the card shows: the errors, "1 to fix", while there are any (`usePlaneShell`'s `report`). Its
 * key is their sentences, so a rebuild that changes them is a new alert.
 *
 * @param {readonly object[] | null} findings
 * @returns {{ alert: object } | null}
 */
export function findingsReport(findings) {
  const errors = (findings || []).filter(findingBlocks);
  if (!errors.length) return null;
  return {
    alert: { severity: "error", blocking: false, kind: "findings", report: false, title: `${errors.length} to fix`, message: "",
      key: JSON.stringify(errors.map((finding) => finding.summary || finding.description)) },
  };
}

function FindingsSection({ heading, findings, onChoose }) {
  if (!findings.length) return null;
  return <section className="min-w-0">
    {heading ? <h3 className="mb-1 text-xs font-normal leading-4 text-muted-foreground">{heading}</h3> : null}
    <ul className="-mx-2 flex min-w-0 flex-col">
      {findings.map((finding) => <li key={finding.index} className="min-w-0">
        <button type="button" onClick={() => onChoose(finding)} data-finding-row={finding.index}
          className={cn("w-full rounded-md px-2 py-1 text-left text-sm leading-5 text-foreground break-words whitespace-normal",
            "hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}>
          {finding.summary || finding.description}
        </button>
      </li>)}
    </ul>
  </section>;
}

/** The card's body: what to fix before ordering. */
export default function FindingsList({ findings, onChoose }) {
  return <div className="flex min-w-0 flex-col gap-3" data-findings="">
    <FindingsSection heading="Fix before ordering" findings={(findings || []).filter(findingBlocks)} onChoose={onChoose} />
  </div>;
}

// One natural order for what a group names: C2 before C10.
const NATURAL = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
const SHOWN_REFS = 4;

/** What a reference reads as in a list: `#U3.9` is U3, `#net:VIN` is VIN. */
const refName = (ref) => ref.replace(/^#/, "").replace(/^net:/, "").replace(/\..*$/, "");

/**
 * The suggestions grouped by kind (their check and KiCad's type), in the order each first appears:
 * KiCad reports a silkscreen clearance once per pair, so a board says it twenty times. A group reads
 * as its findings' one sentence, else their shared message, else the review check's name
 * (`REVIEW_KINDS`); under it, what it is about (its parts and nets, once each). It is chosen as one
 * finding whose items are all of its findings'.
 */
export function groupFindings(findings) {
  const groups = new Map();
  for (const finding of findings) {
    const kind = `${finding.check}:${finding.type}`;
    const group = groups.get(kind) || { kind, findings: [] };
    group.findings.push(finding);
    groups.set(kind, group);
  }
  return [...groups.values()].map((group) => {
    const sentence = groupSentence(group.findings);
    const refs = [...new Set(group.findings.flatMap((finding) => finding.items.map((item) => item.ref).filter(Boolean).map(refName)))].sort(NATURAL.compare);
    return { ...group, sentence, refs, chosen: { ...group.findings[0], items: group.findings.flatMap((finding) => finding.items) } };
  });
}

// What a group of the review's own checks is called when each of its findings says it in its own words
// (KiCad's checks share one message per type).
const REVIEW_KINDS = Object.freeze({
  decoupling_missing: "No decoupling capacitor",
  decoupling_far: "Decoupling capacitor too far",
  track_current: "Track too thin for its current",
});

function groupSentence(findings) {
  const sentences = new Set(findings.map((finding) => finding.summary || finding.description));
  if (sentences.size === 1) return [...sentences][0];
  const descriptions = new Set(findings.map((finding) => finding.description));
  return descriptions.size === 1 ? [...descriptions][0] : REVIEW_KINDS[findings[0].type] || findings[0].type.replaceAll("_", " ");
}

const namesOf = (refs) => (refs.length > SHOWN_REFS ? `${refs.slice(0, SHOWN_REFS).join(", ")} +${refs.length - SHOWN_REFS}` : refs.join(", "));

/** Select's Checks panel: the suggestions, folded until a person opens it, one row per kind of finding. */
export function ChecksPanel({ findings, onChoose, active }) {
  const groups = useMemo(() => groupFindings((findings || []).filter((finding) => !findingBlocks(finding))), [findings]);
  if (!groups.length) return null;
  return <ToolPanel id="checks" title="Checks" label="Checks" defaultCollapsed hidden={!active}>
    <ul className="flex min-w-0 flex-col px-1 pb-1 text-tiny" data-checks="">
      {groups.map((group) => <li key={group.kind} className="min-w-0">
        <button type="button" onClick={() => onChoose(group.chosen)} data-finding-row={group.chosen.index}
          aria-label={group.sentence}
          className="flex w-full min-w-0 flex-col rounded-sm px-2 py-1 text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <span className="flex w-full min-w-0 items-baseline gap-1.5">
            <span className="min-w-0 flex-1 break-words text-foreground">{group.sentence}</span>
            {group.findings.length > 1 ? <span className="shrink-0 tabular-nums text-muted-foreground">{group.findings.length}</span> : null}
          </span>
          {group.refs.length ? <span className="min-w-0 truncate text-micro text-muted-foreground">{namesOf(group.refs)}</span> : null}
        </button>
      </li>)}
    </ul>
  </ToolPanel>;
}
