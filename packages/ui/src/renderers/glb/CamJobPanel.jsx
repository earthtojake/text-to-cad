import { CircleCheck, CircleX, Eye, EyeOff } from "lucide-react";
import { cn } from "@text-to-cad/ui/utils";
import { Button } from "@text-to-cad/ui/primitives/button";
import { ROW_NAME_UNDER_ACTIONS, TREE_INDENT_PX, TreeRowGuides, TreeRowLabel, TreeRowSurface, treeRowActionsClass } from "@text-to-cad/ui/primitives/tree-row";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import ToolPanel, { ToolPanelClose } from "../kit/tools/ToolPanel.jsx";
import { assumedWords, formatDuration, jobSummary, operationDetail, toolSpeeds } from "./cam/extras.js";

// The panel's id: Job keeps the tree's, as FEA's Study does, so the stack sizes it as Select's tree.
export const CAM_JOB_PANEL_ID = "tree";

// The verdict's status in the theme's own status tones, FEA's verdict's: green to cut, red to fix.
const TONES = Object.freeze({
  ready: { icon: CircleCheck, text: "text-success", surface: "bg-success-bg/70" },
  fix: { icon: CircleX, text: "text-error", surface: "bg-error-bg/70" },
});

const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;
const NONE = Object.freeze(new Set());
// The room an operation row's eye takes at its right end (its `--row-actions`).
const ROW_ACTIONS_WIDTH = "1.5rem";

/** A tool's row: how the machine names it and what it is ("T1 6 mm flat"), its speed and feed beside it. */
export const toolRowLabel = (tool) => [tool.label, tool.plain].filter(Boolean).join(" ");

/** What a row chooses: its id, the operations it isolates, the faces Quick Edit names and the sentence it reads. */
const opChoice = (op) => ({ id: `op:${op.index}`, ops: [op.index], faces: op.faces, summary: op.summary });

/** The choices the panel's rows make, by row: a setup chooses all its operations; an error, the operation it is about. */
export function camChoices(job) {
  const choices = new Map();
  for (const op of job.operations) choices.set(`op:${op.index}`, opChoice(op));
  for (const setup of job.setups) {
    choices.set(`setup:${setup.id}`, {
      id: `setup:${setup.id}`, ops: setup.operations.map((op) => op.index), faces: [...new Set(setup.operations.flatMap((op) => op.faces))],
      summary: `${setup.plain} setup: ${setup.operations.map((op) => op.plain).join(", ")}, ${formatDuration(setup.timeS)}`,
    });
  }
  // A tool chooses every operation that runs it.
  for (const tool of job.tools || []) {
    const ops = job.operations.filter((op) => tool.operations.includes(op.index));
    const speeds = toolSpeeds(tool).replace(" · ", ", ");
    choices.set(`tool:${tool.id}`, {
      id: `tool:${tool.id}`, ops: ops.map((op) => op.index), faces: [...new Set(ops.flatMap((op) => op.faces))],
      summary: `${toolRowLabel(tool)}${speeds ? ` at ${speeds}` : ""}${ops.length ? `: ${ops.map((op) => op.plain).join(", ")}` : ", unused"}`,
    });
  }
  job.findings.forEach((finding, index) => {
    if (finding.level !== "error") return;
    const ops = job.operations.filter((entry) => (finding.operations || [finding.operation]).includes(entry.index));
    const op = ops[0] || null;
    choices.set(`finding:${index}`, { id: `finding:${index}`, ops: ops.map((entry) => entry.index), faces: [...new Set(ops.flatMap((entry) => entry.faces))],
      summary: op ? `${finding.message} (${ops.map((entry) => entry.summary).join("; ")})` : finding.message });
  });
  return choices;
}

/** A row that chooses on a press, Enter or Space, and says so (`aria-pressed`) while it is the choice. */
function Choosable({ id, label, chosen, onChoose, className, children }) {
  const active = chosen === id;
  return <button type="button" aria-label={`Select ${label}`} aria-pressed={active} data-cam-choice={id} onClick={() => onChoose(id)}
    className={cn("flex min-w-0 flex-1 items-center gap-1.5 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", className)}>
    {children}
  </button>;
}

/**
 * The answer first, as FEA's verdict: the headline in its status' tone ("Ready to cut · 42 min · 3 tools",
 * "2 to fix"), what the job takes ("1 tool change · grbl controller"), whether G-code was written and how many
 * warnings went to the agent, what the plan assumed that nobody stated (one small line each, its reason on hover),
 * then each error in plain words, each a row that chooses the operation it is about.
 */
function CamVerdict({ job, chosen, onChoose }) {
  const tone = TONES[job.verdict.status] || TONES.ready;
  const Icon = tone.icon;
  const errors = job.findings.map((finding, index) => ({ finding, index })).filter(({ finding }) => finding.level === "error");
  const caption = [job.verdict.gcode, job.verdict.warnings ? plural(job.verdict.warnings, "warning") : ""]
    .filter(Boolean).join(" · ");
  const summary = jobSummary(job);
  return <section aria-label="Verdict" data-cam-verdict={job.verdict.status} className={cn("mx-1 mb-1 flex flex-col gap-1 rounded-md px-2.5 py-2", tone.surface)}>
    <div className={cn("flex items-center gap-1.5 text-xs leading-4", tone.text)}>
      <Icon className="size-3.5 shrink-0" strokeWidth={2} aria-hidden="true" />
      <span className="min-w-0 [overflow-wrap:break-word]" data-cam-verdict-title="">{job.verdict.headline}</span>
    </div>
    {summary ? <p className="text-tiny leading-4 text-foreground/80" data-cam-summary="">{summary}</p> : null}
    {caption ? <p className="text-tiny leading-4 text-muted-foreground" data-cam-verdict-caption="">{caption}</p> : null}
    {job.assumed.length ? <ul className="flex flex-col" aria-label="Assumed" data-cam-assumed="">
      {job.assumed.map((entry, index) => <li key={index} title={entry.why || undefined}
        className="min-w-0 text-tiny leading-4 text-muted-foreground [overflow-wrap:anywhere]">Assumed {assumedWords(entry)}</li>)}
    </ul> : null}
    {errors.length ? <ul className="flex flex-col" aria-label="To fix">
      {errors.map(({ finding, index }) => <li key={index} className="min-w-0 border-t border-foreground/10" data-cam-finding={finding.check || "error"}>
        <Choosable id={`finding:${index}`} label={finding.message} chosen={chosen} onChoose={onChoose}
          className={cn("-mx-1 items-start px-1 py-1 text-tiny leading-4 text-error hover:bg-foreground/5", chosen === `finding:${index}` && "bg-foreground/[0.07]")}>
          <CircleX className="mt-0.5 size-3 shrink-0" strokeWidth={2} aria-hidden="true" />
          <span className="min-w-0 [overflow-wrap:break-word]">{finding.message}</span>
        </Choosable>
      </li>)}
    </ul> : null}
  </section>;
}

/**
 * A setup's row (its name and time), an operation's (its colour, its word, its tool and time) or a tool's (its name,
 * its speed and feed), 24px, in the tree's rows. An operation's row has its eye (`onToggleHidden`) floating over its
 * right end as an assembly row's does: on hover, and kept while its paths are put away (`hidden`).
 */
function JobRow({ id, label, detail, hint, swatch = null, depth, chosen, onChoose, hidden = false, onToggleHidden = null }) {
  const eye = hidden ? "Reveal" : "Hide";
  return <li className="min-w-0">
    <TreeRowSurface dense active={chosen === id} className={cn("gap-0 pr-0", onToggleHidden && "group/row")}
      style={{ paddingLeft: depth * TREE_INDENT_PX, ...(onToggleHidden ? { "--row-actions": ROW_ACTIONS_WIDTH } : null) }}
      data-cam-row={id} data-cam-hidden={hidden ? "" : undefined}>
      <TreeRowGuides depth={depth} column={16} />
      <span className="grid h-6 w-4 shrink-0 place-items-center" aria-hidden="true">
        {swatch ? <span className={cn("size-2 rounded-full", hidden && "opacity-40")} style={{ backgroundColor: swatch }} data-cam-swatch="" /> : null}
      </span>
      <TooltipHint content={hint} overflowOnly={!hint}>
        <Choosable id={id} label={label} chosen={chosen} onChoose={onChoose}
          className={cn("h-full pr-2", onToggleHidden && (hidden ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover), hidden && "text-muted-foreground")}>
          <TreeRowLabel className={detail ? "max-w-full shrink-0" : "flex-1"}>{label}</TreeRowLabel>
          {detail ? <TreeRowLabel className="flex-1 text-micro text-muted-foreground tabular-nums">{detail}</TreeRowLabel> : null}
        </Choosable>
      </TooltipHint>
      {onToggleHidden ? <div data-row-actions="" className={treeRowActionsClass(hidden)}>
        <TooltipHint content={eye}>
          <Button type="button" variant="ghost" size="icon-xs" aria-label={`${eye} ${label}`} className="h-5 w-4 text-muted-foreground"
            onClick={(event) => { event.stopPropagation(); onToggleHidden(); }}>
            {hidden ? <EyeOff className="size-3" aria-hidden="true" /> : <Eye className="size-3" aria-hidden="true" />}
          </Button>
        </TooltipHint>
      </div> : null}
    </TreeRowSurface>
  </li>;
}

/** The job's tools under a muted heading, each a row with its speed and feed: the speeds a machinist sets. */
function JobTools({ job, chosen, onChoose }) {
  const tools = job.tools;
  if (!tools?.length) return null;
  return <section aria-label="Tools" className="flex flex-col px-1 pb-1 text-tiny" data-cam-tools="">
    <h3 className="flex h-6 items-center pl-4 text-tiny font-normal text-muted-foreground">Tools</h3>
    <ul>
      {tools.map((tool) => {
        const speeds = toolSpeeds(tool);
        return <JobRow key={tool.id} id={`tool:${tool.id}`} label={toolRowLabel(tool)} detail={speeds}
          hint={[toolRowLabel(tool), speeds, job.operations.filter((op) => tool.operations.includes(op.index)).map((op) => op.name || op.plain).join(", ")]
            .filter(Boolean).join(" · ")} depth={1} chosen={chosen} onChoose={onChoose} />;
      })}
    </ul>
  </section>;
}

/**
 * A CAM result's Select panel, **Job**, closable as the Features tree is: the verdict first, its errors under
 * it, then each setup with its operations under it (the plain word, the tool, the time), in the job's order,
 * then the job's tools with their speeds. Every row is a choice (`onChoose(id)`; `chosen` is the row chosen):
 * it isolates its paths, and Quick Edit gets its faces and its sentence. An operation's swatch is its paths'
 * colour (`colours`, by index), and its Hide/Reveal eye puts its paths away and back (`hidden`, `onToggleHidden(index)`).
 *
 * @param {{ active: boolean, job: object, colours: Record<number, string>, chosen: string, onChoose(id: string): void,
 *   hidden?: Set<number> | null, onToggleHidden?(index: number): void }} props
 */
export default function CamJobPanel({ active, job, colours, chosen, onChoose, hidden = null, onToggleHidden = null }) {
  const away = hidden || NONE;
  return <ToolPanel id={CAM_JOB_PANEL_ID} title="Job" label="Job" actions={<ToolPanelClose />} fit="tree" resizable fitContent closable collapsible={false}
    hidden={!active}>
    <CamVerdict job={job} chosen={chosen} onChoose={onChoose} />
    <ul className="flex flex-col px-1 pb-1 text-tiny" aria-label="Setups">
      {job.setups.map((setup) => <li key={setup.id} className="min-w-0 [&:not(:first-child)]:pt-1">
        <ul>
          <JobRow id={`setup:${setup.id}`} label={setup.plain} detail={`${plural(setup.operations.length, "operation")} · ${formatDuration(setup.timeS)}`}
            depth={0} chosen={chosen} onChoose={onChoose} />
          {setup.operations.map((op) => <JobRow key={op.index} id={`op:${op.index}`} label={op.name || op.plain} detail={operationDetail(op)}
            hint={[op.summary, ...op.limits].filter(Boolean).join(". ")} swatch={colours[op.index]} depth={1} chosen={chosen} onChoose={onChoose}
            hidden={away.has(op.index)} onToggleHidden={onToggleHidden ? () => onToggleHidden(op.index) : null} />)}
        </ul>
      </li>)}
    </ul>
    <JobTools job={job} chosen={chosen} onChoose={onChoose} />
  </ToolPanel>;
}
