import { cn } from "@text-to-cad/ui/utils";

/**
 * What a check found on a design, as the viewer's alert card lists it, the same for a KiCad board
 * and an FEA result: what must be fixed first (the errors, under the renderer's own heading) then
 * the rest ("Suggestions"), each in the order the check gave, each its sentence in full. Choosing
 * one hands it to `onChoose`. A finding is `{ severity, summary, description, index, items }`.
 */

/** Whether a finding must be fixed first: an error, whichever check found it. */
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
 * The alert the card shows for these findings, or null for none: open over the view while there is
 * something to fix, put away (its icon in the navbar) for suggestions alone (see `startDismissed`
 * in `useAlertDismissal`). Its key is the findings' sentences, so a rebuild that changes them is a
 * new alert.
 */
export function findingsAlert(findings) {
  if (!findings?.length) return null;
  const errors = findings.some(findingBlocks);
  return { severity: errors ? "error" : "warning", blocking: false, kind: "findings", report: false, title: findingsLabel(findings), message: "",
    key: JSON.stringify(findings.map((finding) => [finding.severity, finding.summary || finding.description])) };
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

/** `headings`: what the errors are listed under ("Fix before ordering", "Fix before using") and the rest ("Suggestions"). */
export default function FindingsList({ findings, onChoose, headings }) {
  return <div className="flex min-w-0 flex-col gap-3" data-findings="">
    <FindingsSection heading={headings.fix} findings={findings.filter(findingBlocks)} onChoose={onChoose} />
    <FindingsSection heading={headings.suggestions} findings={findings.filter((finding) => !findingBlocks(finding))} onChoose={onChoose} />
  </div>;
}
