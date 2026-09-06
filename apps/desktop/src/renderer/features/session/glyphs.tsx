import {
  BookOpen,
  FileMinus,
  FileSymlink,
  Globe,
  Image as ImageIcon,
  Pencil,
  Sparkles,
  SquareTerminal,
  ToggleLeft,
  Wrench,
} from "lucide-react";
import { cn } from "cn";

import type { Glyph } from "./view";
import type { SubagentState } from "@shared/acp/types";

/**
 * The leading glyph of an activity row (plan §2): pencil for an edit, book
 * for a read, terminal for a command, globe for the web, sparkle for a
 * thought. One map, so every row and every folded line agree.
 */
export function GlyphIcon({ glyph, className }: { glyph: Glyph; className?: string }) {
  const props = { className: cn("size-3.5 shrink-0", className) };
  switch (glyph) {
    case "edit":
      return <Pencil {...props} />;
    case "read":
      return <BookOpen {...props} />;
    case "execute":
      return <SquareTerminal {...props} />;
    case "search":
    case "fetch":
      return <Globe {...props} />;
    case "think":
      return <Sparkles {...props} />;
    case "image":
      return <ImageIcon {...props} />;
    case "delete":
      return <FileMinus {...props} />;
    case "move":
      return <FileSymlink {...props} />;
    case "switch_mode":
      return <ToggleLeft {...props} />;
    case "other":
      return <Wrench {...props} />;
  }
}

/**
 * A subagent's orb: coloured by a hash of its name so the same subagent
 * keeps its colour across rows, pulsing while it runs. Codex draws these
 * as small coloured circles; the hues are the chart tokens so they follow
 * the theme.
 */
export function SubagentOrb({
  name,
  state,
  className,
}: {
  name: string;
  state: SubagentState;
  className?: string;
}) {
  let hash = 0;
  for (const char of name) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  const hue = (hash % 5) + 1;
  return (
    <span
      aria-hidden
      className={cn(
        "inline-block size-2.5 shrink-0 rounded-full",
        state === "running" && "animate-pulse",
        (state === "failed" || state === "disconnected") && "opacity-40",
        className,
      )}
      style={{ backgroundColor: `var(--chart-${hue})` }}
    />
  );
}
