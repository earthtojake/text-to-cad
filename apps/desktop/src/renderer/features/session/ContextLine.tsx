import { useRef, useState } from "react";

import { Popover, PopoverAnchor, PopoverContent } from "@renderer/components/ui/popover";
import type { ContextUsage, TokenTotals, TurnUsage } from "@shared/acp/types";

/**
 * How full the context window is, **above** the box and always the same
 * height. Under it, the line appeared with the first turn and moved every
 * time the composer grew a row, so the thing you were reading walked up the
 * screen as you typed. A reserved line does not move, and an empty one costs
 * ten pixels.
 *
 * The line is one number; the breakdown behind it is the popover — hover to
 * see it, click to keep it. It holds the window as a bar, the agent's own
 * category breakdown when it sends one (`contextUsage.breakdown`, usually
 * absent — see `ContextBreakdownEntrySchema`), and the token accounting of
 * the session: what was fresh input, what was read from cache, what was
 * written to it, what came back. That accounting used to be a chip at the
 * end of every turn, which put a number nobody reads mid-thread into the
 * transcript forty times a session.
 *
 * What a turn cost in dollars is in neither place. It is a number nobody
 * acts on mid-thread, and a price tag on a box someone is about to type into
 * is a poor thing to put in front of them.
 */
export function ContextLine({
  usage,
  sessionUsage,
  lastTurnUsage,
}: {
  usage: ContextUsage | null;
  sessionUsage: TokenTotals | null;
  lastTurnUsage: TurnUsage | null;
}) {
  const anchor = useRef<HTMLButtonElement>(null);
  const [hovered, setHovered] = useState(false);
  const [pinned, setPinned] = useState(false);
  const percent = usage && usage.size > 0 ? Math.min(100, Math.round((usage.used / usage.size) * 100)) : null;
  const open = (hovered || pinned) && percent !== null;

  return (
    <Popover
      onOpenChange={(next) => {
        if (!next) {
          setHovered(false);
          setPinned(false);
        }
      }}
      open={open}
    >
      <div
        className="flex h-3.5 items-center justify-end px-2 font-mono text-[10px] text-muted-foreground/70 tabular-nums"
        data-context-line
      >
        {percent === null || !usage ? null : (
          <PopoverAnchor asChild>
            <button
              className="rounded-sm outline-none hover:text-foreground focus-visible:text-foreground"
              data-context-trigger
              onClick={() => setPinned((current) => !current)}
              onPointerEnter={() => setHovered(true)}
              onPointerLeave={() => setHovered(false)}
              ref={anchor}
              type="button"
            >
              {percent}% context
            </button>
          </PopoverAnchor>
        )}
      </div>
      <PopoverContent
        align="end"
        className="w-80 p-3"
        data-context-popover
        onOpenAutoFocus={(event) => event.preventDefault()}
        onPointerDownOutside={(event) => {
          // A click on the line itself is the pin, not a dismissal.
          if (anchor.current?.contains(event.target as Node)) {
            event.preventDefault();
          }
        }}
        onPointerEnter={() => setHovered(true)}
        onPointerLeave={() => setHovered(false)}
        side="top"
        sideOffset={8}
      >
        {usage ? (
          <ContextBreakdown lastTurnUsage={lastTurnUsage} sessionUsage={sessionUsage} usage={usage} />
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

/** The chart colours, one per category, cycled. Written out so Tailwind sees them. */
const SEGMENT_COLORS = ["bg-chart-1", "bg-chart-2", "bg-chart-3", "bg-chart-4", "bg-chart-5"];

function ContextBreakdown({
  usage,
  sessionUsage,
  lastTurnUsage,
}: {
  usage: ContextUsage;
  sessionUsage: TokenTotals | null;
  lastTurnUsage: TurnUsage | null;
}) {
  const size = usage.size > 0 ? usage.size : null;
  const categories = usage.breakdown ?? [];
  const rows = tokenRows(sessionUsage, lastTurnUsage);

  return (
    <div className="flex flex-col gap-3 text-[12px] leading-4">
      <div className="flex flex-col gap-1.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-medium">Context window</span>
          <span className="font-mono text-[11px] text-muted-foreground tabular-nums" data-context-window>
            {formatTokens(usage.used)} of {size === null ? "?" : formatTokens(size)}
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
        <div className="flex justify-between text-[11px] text-muted-foreground">
          <span>{percentLabel(usage.used, size)} used</span>
          <span>
            {size === null ? "—" : formatTokens(Math.max(0, size - usage.used))} free
          </span>
        </div>
      </div>

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
        <div className="flex flex-col gap-1 border-t pt-2" data-context-tokens>
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <span className="min-w-0 flex-1">Tokens</span>
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
  );
}

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
