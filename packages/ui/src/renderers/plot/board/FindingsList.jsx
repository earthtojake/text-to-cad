import { cn } from "@text-to-cad/ui/utils";

/**
 * What KiCad and the review found on a board or a schematic, as its alert card lists it: what
 * stops an order ("Fix before ordering": the errors) then the rest ("Suggestions"), each in
 * KiCad's order, each its sentence in full. Choosing one hands it to `onChoose`.
 */

/** Whether a finding stops an order: an error, whichever check found it. */
export const findingBlocks = (finding) => finding.severity === "error";

const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** What the card and its navbar icon are called: "2 to fix, 3 suggestions", "1 to fix", "3 suggestions". */
export function findingsLabel(findings) {
  const errors = findings.filter(findingBlocks).length;
  const suggestions = findings.length - errors;
  if (!errors) return plural(suggestions, "suggestion");
  return suggestions ? `${errors} to fix, ${plural(suggestions, "suggestion")}` : `${errors} to fix`;
}

/**
 * What KiCad and the review found, as the shell's report card (`usePlaneShell`'s `report`): open over
 * the board while there is something to fix before ordering, put away (its icon in the navbar) for
 * suggestions alone. Its key is the findings' sentences, so a rebuild that changes them is a new alert.
 *
 * @param {readonly object[] | null} findings
 * @returns {{ alert: object, startDismissed: boolean } | null}
 */
export function findingsReport(findings) {
  if (!findings?.length) return null;
  const errors = findings.some(findingBlocks);
  return {
    alert: { severity: errors ? "error" : "warning", blocking: false, kind: "findings", report: false, title: findingsLabel(findings), message: "",
      key: JSON.stringify(findings.map((finding) => [finding.severity, finding.summary || finding.description])) },
    startDismissed: !errors,
  };
}

function FindingsSection({ heading, findings, onChoose }) {
  if (!findings.length) return null;
  return <section className="min-w-0">
    <h3 className="mb-1 text-xs font-normal leading-4 text-muted-foreground">{heading}</h3>
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

export default function FindingsList({ findings, onChoose }) {
  return <div className="flex min-w-0 flex-col gap-3" data-findings="">
    <FindingsSection heading="Fix before ordering" findings={findings.filter(findingBlocks)} onChoose={onChoose} />
    <FindingsSection heading="Suggestions" findings={findings.filter((finding) => !findingBlocks(finding))} onChoose={onChoose} />
  </div>;
}
