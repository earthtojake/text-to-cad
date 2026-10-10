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

/** Select's Checks panel: the suggestions, folded until a person opens it. */
export function ChecksPanel({ findings, onChoose, active }) {
  const suggestions = (findings || []).filter((finding) => !findingBlocks(finding));
  if (!suggestions.length) return null;
  return <ToolPanel id="checks" title="Checks" label="Checks" defaultCollapsed hidden={!active}>
    <div className="px-2 pb-2" data-checks="">
      <FindingsSection heading={null} findings={suggestions} onChoose={onChoose} />
    </div>
  </ToolPanel>;
}
