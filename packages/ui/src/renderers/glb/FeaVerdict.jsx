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
 * How hard the part is working: the peak over the limit, filled to the limit at most, the part of it
 * past the limit striped, with a tick where the study's margin keeps it ("your 2× margin": the
 * limit over the margin). A meter, for assistive technology, in percent of the limit.
 */
function WorkBar({ use, margin, tone }) {
  const over = use > 1;
  const tick = margin > 1 ? 1 / margin : null;
  // The tick's words stay inside the bar: centred on it, or held to the end it is near.
  const align = tick === null ? "" : tick < 0.3 ? "translate-x-0" : tick > 0.7 ? "-translate-x-full" : "-translate-x-1/2";
  return <div className="flex flex-col gap-0.5">
    <div role="meter" aria-label="How hard the part is working" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(use * 100)}
      aria-valuetext={`${Math.round(use * 100)}% of its limit`} data-fea-verdict-bar="" data-over={over ? "" : undefined}
      className="relative h-1.5 rounded-full bg-foreground/10">
      <div className={cn("absolute inset-y-0 left-0 rounded-full", tone.fill)} style={{ width: percent(use) }} data-fea-verdict-fill="">
        {over ? <div className="absolute inset-y-0 right-0 w-1/4 rounded-r-full"
          style={{ backgroundImage: "repeating-linear-gradient(-45deg, transparent 0 2px, color-mix(in oklab, var(--background) 60%, transparent) 2px 4px)" }} /> : null}
      </div>
      {tick !== null ? <span className="absolute -top-0.5 h-2.5 w-px bg-foreground/55" style={{ left: percent(tick) }} data-fea-verdict-tick="" aria-hidden="true" /> : null}
    </div>
    {tick !== null ? <div className="relative h-3.5 text-micro leading-3.5 text-muted-foreground" aria-hidden="true">
      <span className={cn("absolute top-0 whitespace-nowrap", align)} style={{ left: percent(tick) }}>your {String(margin)}× margin</span>
    </div> : null}
  </div>;
}

/**
 * The answer at a glance, at the top of Study (`feaVerdict`): a status word with its icon, the
 * weakest part in an assembly, the peak against the limit, how hard the part is working and how
 * much of this load it would hold. It follows the load shown.
 */
export default function FeaVerdict({ verdict }) {
  const tone = TONES[verdict.status];
  const Icon = tone.icon;
  return <section aria-label="Verdict" data-fea-verdict={verdict.status} className={cn("mx-1 mb-1 flex flex-col gap-1.5 rounded-md px-2 py-2", tone.surface)}>
    <div className="flex min-w-0 flex-col gap-0.5">
      <div className={cn("flex items-center gap-1.5 text-xs leading-4", tone.text)}>
        <Icon className="size-3.5 shrink-0" strokeWidth={2} aria-hidden="true" />
        <span className="min-w-0" data-fea-verdict-title="">{verdict.title}</span>
      </div>
      {verdict.part ? <p className="min-w-0 text-tiny leading-4 text-foreground [overflow-wrap:break-word]" data-fea-verdict-part="">Weakest: {verdict.part}</p> : null}
      <p className="text-tiny leading-4 text-muted-foreground tabular-nums" data-fea-verdict-line="">{verdict.line}</p>
    </div>
    {verdict.status !== "none" ? <WorkBar use={verdict.use} margin={verdict.margin} tone={tone} /> : null}
    {verdict.caption ? <p className="text-tiny leading-4 text-foreground" data-fea-verdict-caption="">{verdict.caption}</p> : null}
  </section>;
}
