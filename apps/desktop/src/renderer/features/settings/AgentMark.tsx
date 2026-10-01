/**
 * An agent's mark: its own logo, on a neutral rounded field.
 *
 * The logos come from the public ACP registry and are committed under
 * `src/renderer/assets/agents/` (`scripts/fetch-agent-icons.mjs`). Every one of
 * them is drawn in `currentColor`, so they are inlined as markup and take the
 * colour of the text around them — one asset that reads in both themes rather
 * than a light and a dark copy of each.
 *
 * Two agents in the table have no registry logo. They fall back to a letter on
 * a tinted field, which is legible at 20 px and never a broken square.
 */
import { cn } from "cn";

import { agentIcon } from "@renderer/lib/agent-icons";

/** The tint for a letter mark, chosen by hashing the id across the chart tokens. */
const TINTS = [
  "bg-chart-1/15 text-chart-1",
  "bg-chart-2/15 text-chart-2",
  "bg-chart-3/15 text-chart-3",
  "bg-chart-4/15 text-chart-4",
  "bg-chart-5/15 text-chart-5",
];

function tintFor(id: string): string {
  let hash = 0;
  for (const character of id) {
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  }
  return TINTS[hash % TINTS.length] ?? TINTS[0]!;
}

/** The field, and the glyph inside it, per place the mark is used. */
const SIZES = {
  row: { field: "size-7 rounded-md", glyph: "size-5", letter: "text-[13px]" },
  drawer: { field: "size-10 rounded-lg", glyph: "size-8", letter: "text-base" },
} as const;

export function AgentMark({
  id,
  name,
  icon,
  size = "row",
  className,
}: {
  id: string;
  name: string;
  /** The registry's `icon` column; null draws the letter. */
  icon?: string | null;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  const markup = agentIcon(icon);
  const dimensions = SIZES[size];

  if (!markup) {
    return (
      <span
        aria-hidden
        className={cn(
          "flex shrink-0 items-center justify-center font-semibold",
          dimensions.field,
          dimensions.letter,
          tintFor(id),
          className,
        )}
      >
        {name.slice(0, 1).toUpperCase()}
      </span>
    );
  }

  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center bg-muted text-foreground",
        dimensions.field,
        className,
      )}
    >
      {/* Committed assets, checked for script and for remote references by the
          script that downloads them — not user input. */}
      <span
        className={cn("block", dimensions.glyph)}
        dangerouslySetInnerHTML={{ __html: markup }}
      />
    </span>
  );
}
