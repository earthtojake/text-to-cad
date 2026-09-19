import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "cn";

import { Popover, PopoverContent, PopoverTrigger } from "@renderer/components/ui/popover";
import type { ContextUsage, RateLimit, TokenTotals, TurnUsage } from "@shared/acp/types";

/**
 * How full the context window is: a 16px ring at the end of the composer's
 * row, and a panel behind it (Claude Code's).
 *
 * The ring replaces a line of text reading `3% context`. A number nobody is
 * mid-sentence about does not need a word beside it — the arc says full or
 * not at a glance, its colour says whether that matters, and the number is
 * the tooltip. It costs sixteen pixels at the end of a row that was already
 * there, rather than a reserved line above the box.
 *
 * The panel opens on **click** and stays open — hover does nothing. It is
 * something to read and to compare rows in, not a thing to glance at: a
 * popover that closes when the pointer leaves cannot be read down its
 * length. Escape, a click outside, or the ring again dismisses it.
 *
 * Three things are in it, in the order somebody wants them: the window,
 * the account's plan limits when the agent reports any, and — behind
 * `See detailed breakdown` — the agent's own categories and the session's
 * token accounting. The accounting used to be a chip at the end of every
 * turn, which put a number nobody reads mid-thread into the transcript
 * forty times a session.
 *
 * What a turn cost in dollars is in none of them. It is a number nobody
 * acts on mid-thread, and a price tag on a box someone is about to type
 * into is a poor thing to put in front of them.
 */
export function ContextMeter({
  sessionId,
  usage,
  sessionUsage,
  lastTurnUsage,
  rateLimits,
}: {
  /** Which session's `See detailed breakdown` state to remember. */
  sessionId: string;
  usage: ContextUsage | null;
  sessionUsage: TokenTotals | null;
  lastTurnUsage: TurnUsage | null;
  rateLimits: Record<string, RateLimit>;
}) {
  const [open, setOpen] = useState(false);
  const [detailed, setDetailed] = useState(() => DETAILED.get(sessionId) ?? false);
  // When the panel was opened, so "Resets in 4 hr 5 min" is a number read
  // off a clock rather than one recomputed on every render of the row.
  const [openedAt, setOpenedAt] = useState(0);
  const fraction = usage && usage.size > 0 ? Math.min(1, usage.used / usage.size) : null;

  // Nothing has been used yet: no ring, no panel. An empty ring beside a
  // fresh session is a gauge reading zero of nothing.
  if (fraction === null || !usage) {
    return null;
  }
  const percent = Math.round(fraction * 100);

  return (
    <Popover
      onOpenChange={(next) => {
        if (next) {
          setOpenedAt(Date.now());
        }
        setOpen(next);
      }}
      open={open}
    >
      <PopoverTrigger asChild>
        <button
          aria-label={`Context ${percent}% used`}
          className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground outline-none transition-colors hover:bg-accent data-[state=open]:bg-accent"
          data-context-trigger
          title={`${formatTokens(usage.used)} / ${formatTokens(usage.size)} (${percent}%)`}
          type="button"
        >
          <Ring fraction={fraction} />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-80 p-3"
        data-context-popover
        onOpenAutoFocus={(event) => event.preventDefault()}
        side="top"
        sideOffset={8}
      >
        <ContextPanel
          detailed={detailed}
          lastTurnUsage={lastTurnUsage}
          now={openedAt}
          onDetailed={(next) => {
            DETAILED.set(sessionId, next);
            setDetailed(next);
          }}
          rateLimits={rateLimits}
          sessionUsage={sessionUsage}
          usage={usage}
        />
      </PopoverContent>
    </Popover>
  );
}

/**
 * Whether the breakdown was left open, per session, for as long as this
 * window lives. Not a setting and not a row in the database: it is where
 * somebody left a disclosure triangle, and it should survive switching
 * threads and come back closed tomorrow.
 */
const DETAILED = new Map<string, boolean>();

/* -------------------------------------------------------------------------- */
/* The ring                                                                    */
/* -------------------------------------------------------------------------- */

export type MeterTone = "muted" | "warning" | "danger";

/** Every tone as a token, so light and dark are the theme's business. */
const TONE_COLOR: Record<MeterTone, string> = {
  muted: "var(--muted-foreground)",
  warning: "var(--foreground-warning)",
  danger: "var(--destructive)",
};

/**
 * The ring's colour by how full the window is: quiet under half, a warning
 * from there, and the destructive colour once there is a fifth left — which
 * is roughly where a long thread starts losing its beginning.
 */
export function ringTone(fraction: number): MeterTone {
  if (fraction >= 0.8) {
    return "danger";
  }
  return fraction >= 0.5 ? "warning" : "muted";
}

/**
 * A plan limit's bar runs later than the window's ring: an account at 60% of
 * its week is fine, and the colour should mean "soon" rather than "much".
 */
export function limitTone(fraction: number): MeterTone {
  if (fraction >= 0.9) {
    return "danger";
  }
  return fraction >= 0.7 ? "warning" : "muted";
}

/** 16px: a track, and an arc of it clockwise from noon. */
function Ring({ fraction }: { fraction: number }) {
  const circumference = 2 * Math.PI * RING_RADIUS;
  return (
    <svg aria-hidden className="size-4" data-context-ring viewBox="0 0 16 16">
      <circle
        cx="8"
        cy="8"
        fill="none"
        opacity={0.3}
        r={RING_RADIUS}
        stroke="var(--muted-foreground)"
        strokeWidth="2"
      />
      <circle
        cx="8"
        cy="8"
        fill="none"
        r={RING_RADIUS}
        stroke={TONE_COLOR[ringTone(fraction)]}
        strokeDasharray={`${circumference * fraction} ${circumference}`}
        strokeLinecap="round"
        strokeWidth="2"
        transform="rotate(-90 8 8)"
      />
    </svg>
  );
}

const RING_RADIUS = 6;

/* -------------------------------------------------------------------------- */
/* The panel                                                                   */
/* -------------------------------------------------------------------------- */

/** The chart colours, one per category, cycled. Written out so Tailwind sees them. */
const SEGMENT_COLORS = ["bg-chart-1", "bg-chart-2", "bg-chart-3", "bg-chart-4", "bg-chart-5"];

function ContextPanel({
  usage,
  sessionUsage,
  lastTurnUsage,
  rateLimits,
  detailed,
  now,
  onDetailed,
}: {
  usage: ContextUsage;
  sessionUsage: TokenTotals | null;
  lastTurnUsage: TurnUsage | null;
  rateLimits: Record<string, RateLimit>;
  detailed: boolean;
  /** The clock the resets are counted from: when the panel was opened. */
  now: number;
  onDetailed: (next: boolean) => void;
}) {
  const size = usage.size > 0 ? usage.size : null;
  const categories = usage.breakdown ?? [];
  const rows = tokenRows(sessionUsage, lastTurnUsage);
  const limits = orderedLimits(rateLimits);
  const overage = limits.some((limit) => limit.isUsingOverage);

  return (
    <div className="flex flex-col gap-3 text-[12px] leading-4">
      <div className="flex flex-col gap-1.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-medium">Context window</span>
          <span className="font-mono text-[11px] text-muted-foreground tabular-nums" data-context-window>
            {formatTokens(usage.used)} / {size === null ? "?" : formatTokens(size)} (
            {percentLabel(usage.used, size)})
          </span>
        </div>
        <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted" data-context-bar>
          {categories.length > 0
            ? categories.map((entry, index) => (
                <div
                  className={SEGMENT_COLORS[index % SEGMENT_COLORS.length]}
                  key={entry.id}
                  style={{ width: `${share(entry.tokens, size)}%` }}
                />
              ))
            : (
                <div className="bg-foreground/60" style={{ width: `${share(usage.used, size)}%` }} />
              )}
        </div>
      </div>

      {limits.length > 0 ? (
        <div className="flex flex-col gap-2 border-t pt-2.5" data-rate-limits>
          <span className="font-medium">Plan usage limits</span>
          {limits.map((limit) => (
            <LimitRow key={limit.type} limit={limit} now={now} />
          ))}
          {overage ? (
            <span className="text-[11px] text-muted-foreground" data-rate-limit-overage>
              Using overage
            </span>
          ) : null}
        </div>
      ) : null}

      {categories.length > 0 || rows.length > 0 ? (
        <div className="flex flex-col gap-2 border-t pt-2.5">
          <button
            aria-expanded={detailed}
            className="-mx-1 flex items-center gap-1 rounded-sm px-1 py-0.5 text-left text-muted-foreground outline-none hover:text-foreground focus-visible:text-foreground"
            data-context-detail-toggle
            onClick={() => onDetailed(!detailed)}
            type="button"
          >
            <ChevronRight className={cn("size-3 transition-transform", detailed && "rotate-90")} />
            See detailed breakdown
          </button>
          {detailed ? (
            <div className="flex flex-col gap-3" data-context-detail>
              {categories.length > 0 ? (
                <div className="flex flex-col gap-1" data-context-categories>
                  {categories.map((entry, index) => (
                    <div className="flex items-center gap-2" data-context-category={entry.id} key={entry.id}>
                      <span
                        className={`size-2 shrink-0 rounded-[2px] ${SEGMENT_COLORS[index % SEGMENT_COLORS.length]}`}
                      />
                      <span className="min-w-0 flex-1 truncate">{entry.name}</span>
                      <span className="font-mono text-[11px] tabular-nums">{formatTokens(entry.tokens)}</span>
                      <span className="w-10 text-right font-mono text-[11px] text-muted-foreground tabular-nums">
                        {percentLabel(entry.tokens, size)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}

              {rows.length > 0 ? (
                <div className="flex flex-col gap-1" data-context-tokens>
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                    <span className="min-w-0 flex-1 font-medium text-foreground">Tokens</span>
                    <span className="w-12 text-right">Session</span>
                    <span className="w-12 text-right">Last turn</span>
                  </div>
                  {rows.map((row) => (
                    <div className="flex items-center gap-2" data-context-token-row={row.id} key={row.id}>
                      <span className="min-w-0 flex-1 truncate">{row.name}</span>
                      <span className="w-12 text-right font-mono text-[11px] tabular-nums">
                        {formatTokens(row.session)}
                      </span>
                      <span className="w-12 text-right font-mono text-[11px] text-muted-foreground tabular-nums">
                        {row.turn === null ? "—" : formatTokens(row.turn)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** One plan limit: what it is, when it comes back, how much of it is gone. */
function LimitRow({ limit, now }: { limit: RateLimit; now: number }) {
  const percent = Math.round(limit.utilization * 100);
  return (
    <div className="flex flex-col gap-1" data-rate-limit={limit.type}>
      <div className="flex items-baseline gap-2">
        <span className="min-w-0 flex-1 truncate">{rateLimitLabel(limit.type)}</span>
        {limit.resetsAt === null ? null : (
          <span className="shrink-0 text-[11px] text-muted-foreground">
            {formatReset(limit.resetsAt, now)}
          </span>
        )}
        <span className="w-8 shrink-0 text-right font-mono text-[11px] tabular-nums">{percent}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full"
          style={{
            background: TONE_COLOR[limitTone(limit.utilization)],
            width: `${Math.max(0, Math.min(100, limit.utilization * 100))}%`,
          }}
        />
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Plan limits                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * The order the limits read in: the one that bites first, then the week,
 * then the week's per-model slices. Anything the SDK grows later sorts by
 * name at the end rather than jumping the queue.
 */
const LIMIT_ORDER = ["five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"];

export function orderedLimits(limits: Record<string, RateLimit>): RateLimit[] {
  const rest = Object.keys(limits)
    .filter((type) => !LIMIT_ORDER.includes(type))
    .sort();
  return [...LIMIT_ORDER, ...rest].flatMap((type) => (limits[type] ? [limits[type]] : []));
}

/**
 * What a limit is called. The four the SDK ships are named outright; a type
 * that arrives after this build is derived from its own name — anything
 * `seven_day_*` is a slice of the week, everything else is its words with a
 * capital — because a limit the person is being held to should say what it
 * is rather than print `seven_day_haiku`.
 */
export function rateLimitLabel(type: string): string {
  if (type === "five_hour") {
    return "5-hour limit";
  }
  if (type === "seven_day") {
    return "Weekly · all models";
  }
  if (type.startsWith("seven_day_")) {
    return `Weekly · ${words(type.slice("seven_day_".length))}`;
  }
  return words(type);
}

function words(type: string): string {
  const text = type.replace(/_/g, " ").trim();
  return text ? text[0]!.toUpperCase() + text.slice(1) : type;
}

const WEEKDAY = new Intl.DateTimeFormat("en-US", { weekday: "short" });
const CLOCK = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });

/**
 * "Resets in 4 hr 5 min" while that is a thing somebody can wait out, and
 * "Resets Fri 3:00 AM" — local — once it is not. A day away in hours is a
 * number to convert; a weekday and a time is a plan.
 */
export function formatReset(resetsAt: number, now: number): string {
  const minutes = Math.round((resetsAt - now) / 60_000);
  if (minutes <= 0) {
    return "Resetting now";
  }
  if (minutes < 24 * 60) {
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    if (hours === 0) {
      return `Resets in ${rest} min`;
    }
    return rest === 0 ? `Resets in ${hours} hr` : `Resets in ${hours} hr ${rest} min`;
  }
  const at = new Date(resetsAt);
  return `Resets ${WEEKDAY.format(at)} ${CLOCK.format(at)}`;
}

/* -------------------------------------------------------------------------- */
/* Tokens                                                                      */
/* -------------------------------------------------------------------------- */

type TokenRow = { id: string; name: string; session: number; turn: number | null };

/**
 * The four ways a turn spends tokens, session total beside last turn. A row
 * the agent never reported — Codex sends no cache writes — is left out
 * rather than printed as a zero.
 */
function tokenRows(session: TokenTotals | null, last: TurnUsage | null): TokenRow[] {
  if (!session) {
    return [];
  }
  const rows: TokenRow[] = [
    { id: "input", name: "Fresh input", session: session.inputTokens, turn: last?.inputTokens ?? null },
    {
      id: "cache-read",
      name: "Cache reads",
      session: session.cachedReadTokens,
      turn: last?.cachedReadTokens ?? null,
    },
    {
      id: "cache-write",
      name: "Cache writes",
      session: session.cachedWriteTokens,
      turn: last?.cachedWriteTokens ?? null,
    },
    { id: "output", name: "Output", session: session.outputTokens, turn: last?.outputTokens ?? null },
  ];
  return rows.filter((row) => row.session > 0 || (row.turn ?? 0) > 0);
}

/**
 * "31.5k", "258.4k", "1M", "522". One decimal, because this is the view
 * somebody opened to see the numbers: rounding 31,500 to "32k" here would
 * throw away the digit they came for.
 */
export function formatTokens(count: number): string {
  if (count < 1_000) {
    return String(count);
  }
  const [value, unit] = count < 1_000_000 ? [count / 1_000, "k"] : [count / 1_000_000, "M"];
  return `${Number(value.toFixed(1))}${unit}`;
}

function share(tokens: number, size: number | null): number {
  if (size === null || size <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(100, (tokens / size) * 100));
}

/** "3%" — and "<1%" rather than "0%" for something that is there but small. */
function percentLabel(tokens: number, size: number | null): string {
  if (size === null || size <= 0) {
    return "—";
  }
  const value = (tokens / size) * 100;
  if (value > 0 && value < 1) {
    return "<1%";
  }
  return `${Math.round(value)}%`;
}
