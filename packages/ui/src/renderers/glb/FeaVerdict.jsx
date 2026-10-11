import { CircleCheck, CircleMinus, CircleX, TriangleAlert } from "lucide-react";
import { cn } from "@text-to-cad/ui/utils";

// Each status in the theme's own status tones, the findings card's and its alert icon's: red to
// fix, amber to watch, green for a pass, and no tone where there is nothing to judge.
const TONES = Object.freeze({
  weak: { icon: CircleX, text: "text-error", fill: "bg-error", surface: "bg-error-bg/70" },
  close: { icon: TriangleAlert, text: "text-warning", fill: "bg-warning", surface: "bg-warning-bg/70" },
  strong: { icon: CircleCheck, text: "text-success", fill: "bg-success", surface: "bg-success-bg/70" },
  none: { icon: CircleMinus, text: "text-muted-foreground", fill: "bg-muted-foreground", surface: "bg-muted/60" },
});

const percent = (fraction) => `${(Math.min(Math.max(fraction, 0), 1) * 100).toFixed(1)}%`;

/**
 * How much of its limit a check uses, as a thin bar: filled to the limit at most, the part past it
 * striped, with a tick where the study's margin keeps a stress check (the limit over the margin). A
 * meter, for assistive technology, in percent of the limit.
 */
function WorkBar({ use, margin, tone, label }) {
  const over = use > 1;
  const tick = margin > 1 ? 1 / margin : null;
  return <div role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(use * 100)}
    aria-valuetext={`${Math.round(use * 100)}% of its limit${tick !== null ? `, your ${String(margin)}× margin at ${Math.round(tick * 100)}%` : ""}`}
    data-fea-verdict-bar="" data-over={over ? "" : undefined} className="relative h-1 rounded-full bg-foreground/10">
    <div className={cn("absolute inset-y-0 left-0 rounded-full", tone.fill)} style={{ width: percent(use) }} data-fea-verdict-fill="">
      {over ? <div className="absolute inset-y-0 right-0 w-1/4 rounded-r-full"
        style={{ backgroundImage: "repeating-linear-gradient(-45deg, transparent 0 2px, color-mix(in oklab, var(--background) 60%, transparent) 2px 4px)" }} /> : null}
    </div>
    {tick !== null ? <span className="absolute -top-0.5 h-2 w-px bg-foreground/55" style={{ left: percent(tick) }} data-fea-verdict-tick="" aria-hidden="true" /> : null}
  </div>;
}

/**
 * A check's row, chosen on a press, Enter or Space (`choice`: its faces and its sentence, for Quick
 * Edit), as Study's rows choose theirs. It holds a meter, so it is a button by role rather than a
 * <button>.
 */
function Choosable({ choice, chosen, onChoose, label, className, children }) {
  if (!choice || !onChoose) return <div className={className}>{children}</div>;
  const active = chosen === choice.id;
  const choose = () => onChoose(choice);
  return <div role="button" tabIndex={0} aria-pressed={active} aria-label={`Select ${label}`} data-fea-choice={choice.id} onClick={choose}
    onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); } }}
    className={cn(className, "-mx-1 cursor-pointer rounded px-1 outline-none hover:bg-foreground/5 focus-visible:ring-2 focus-visible:ring-ring",
      active && "bg-foreground/[0.07]")}>{children}</div>;
}

/**
 * One check, each the same way: its status icon and name in its own tone (so a passing check under a
 * failing headline reads as passing), a thin bar of how much of its limit it uses, and its value
 * against its limit. An assembly's part a stress check is about is its choice's to say, and its tint's.
 */
function CheckRow({ row, chosen, onChoose }) {
  const tone = TONES[row.status];
  const Icon = tone.icon;
  return <li className="min-w-0 border-t border-foreground/10 pt-1" data-fea-check={row.status} data-fea-check-kind={row.kind}>
    <Choosable choice={row.choice} chosen={chosen} onChoose={onChoose} label={row.label} className="flex min-w-0 flex-col gap-1 py-1">
      <div className={cn("flex min-w-0 items-center gap-1.5 text-tiny leading-4", tone.text)}>
        <Icon className="size-3 shrink-0" strokeWidth={2} aria-hidden="true" />
        <span className="min-w-0 [overflow-wrap:break-word]" data-fea-check-label="">{row.label}</span>
      </div>
      <WorkBar use={row.use} margin={row.margin} tone={tone} label={`${row.label}: how much of its limit`} />
      <p className="min-w-0 text-micro leading-3.5 text-muted-foreground tabular-nums [overflow-wrap:break-word]" data-fea-check-line="">{row.line}</p>
    </Choosable>
  </li>;
}

/**
 * The answer at a glance, at the top of Study (`feaVerdict`): the headline in the worst check's tone
 * ("Fails both checks", "Strong enough"), what it means for the load ("OK only to 0.4× this load"),
 * then each check as one row, each chosen on a press (`chosen`, `onChoose`) so what it says goes to
 * Quick Edit with the faces it is about. It follows the load shown.
 */
export default function FeaVerdict({ verdict, chosen = "", onChoose = null }) {
  const tone = TONES[verdict.status];
  const Icon = tone.icon;
  return <section aria-label="Verdict" data-fea-verdict={verdict.status} className={cn("mx-1 mb-2 flex flex-col gap-1.5 rounded-md px-2.5 pb-1.5 pt-2.5", tone.surface)}>
    <div className="flex min-w-0 flex-col gap-1 pb-1">
      <div className={cn("flex items-center gap-1.5 text-xs font-medium leading-4", tone.text)}>
        <Icon className="size-3.5 shrink-0" strokeWidth={2} aria-hidden="true" />
        <span className="min-w-0" data-fea-verdict-title="">{verdict.title}</span>
      </div>
      {verdict.caption ? <p className="text-tiny leading-4 text-foreground" data-fea-verdict-caption="">{verdict.caption}</p> : null}
    </div>
    {verdict.rows.length ? <ul className="flex flex-col" aria-label="Checks">{verdict.rows.map((row) => <CheckRow key={row.id} row={row} chosen={chosen} onChoose={onChoose} />)}</ul> : null}
  </section>;
}
