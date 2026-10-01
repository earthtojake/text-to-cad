import {
  BookOpen,
  Bot,
  CircleCheck,
  CircleX,
  FileMinus,
  FileSymlink,
  Globe,
  Image as ImageIcon,
  Pencil,
  Ellipsis,
  SquareTerminal,
  ToggleLeft,
  Wrench,
} from "lucide-react";
import { cn } from "cn";

import type { Glyph } from "./view";
import type { SubagentState } from "@shared/acp/types";

/**
 * The leading glyph of an activity row (plan §2): pencil for an edit, book
 * for a read, terminal for a command (a `delete` that is a shell line
 * included), globe for the web, ellipsis for a thought, a bot for a call
 * that hands work to a subagent. One map, so every row and every folded line agree.
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
      return <Ellipsis {...props} />;
    case "subagent":
      return <Bot {...props} />;
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
 * A subagent's mark. While it works: an orb coloured by a hash of its name,
 * so the same subagent keeps its colour across rows, pulsing — the colour is
 * identity, never status. Once it stops, the mark says how: a green check
 * for finished, a red cross for failed, a dimmed orb for cancelled or
 * disconnected. (A finished subagent used to keep its hue, which came out
 * amber in dark and navy in light and read as a warning.)
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
  if (state === "completed") {
    return <CircleCheck aria-hidden className={cn("size-3.5 shrink-0 text-success", className)} data-subagent-mark="completed" />;
  }
  if (state === "failed") {
    return <CircleX aria-hidden className={cn("size-3.5 shrink-0 text-destructive", className)} data-subagent-mark="failed" />;
  }
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
        state === "disconnected" || state === "cancelled" ? "opacity-40" : null,
        className,
      )}
      data-subagent-mark={state}
      style={{ backgroundColor: `var(--chart-${hue})` }}
    />
  );
}
