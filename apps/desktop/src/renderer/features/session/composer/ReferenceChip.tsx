import { NodeViewWrapper, type NodeViewProps } from "@tiptap/react";
import { Box, Hash } from "lucide-react";

import { cn } from "@renderer/lib/utils";
import type { CadReference } from "@shared/cad-refs";

import { referenceToken } from "./references";

/**
 * How a reference looks in the composer: a file icon, the file's name and
 * the selector as a badge — `bracket.step` `o1.2`. A bare selector (`#o1.2`,
 * the current file's) shows a hash instead of a file. The whole token is
 * the tooltip, and the chip is what the arrow keys land on; `selected` is
 * ProseMirror's NodeSelection, drawn as a ring so a keyboard user can see
 * what Delete would remove.
 */
export function ReferenceChip({ node, selected }: NodeViewProps) {
  const reference = node.attrs as CadReference;
  const name = reference.file ? (reference.file.split("/").pop() ?? reference.file) : "";
  return (
    <NodeViewWrapper
      as="span"
      className={cn(
        "mx-px inline-flex max-w-full items-center gap-1 rounded-md border bg-secondary/70 px-1.5 py-px align-baseline text-[12px] leading-4 text-secondary-foreground select-none",
        selected && "ring-2 ring-ring ring-offset-1 ring-offset-background",
      )}
      contentEditable={false}
      data-file={reference.file}
      data-reference-chip=""
      data-selected={selected ? "" : undefined}
      data-selector={reference.selector}
      title={referenceToken(reference)}
    >
      {name ? (
        <>
          <Box aria-hidden className="size-3 shrink-0 opacity-70" />
          <span className="max-w-[160px] truncate">{name}</span>
        </>
      ) : (
        <Hash aria-hidden className="size-3 shrink-0 opacity-70" />
      )}
      {reference.selector ? (
        <span className="rounded-sm bg-primary/10 px-1 font-mono text-[11px] text-primary" data-selector-badge>
          {reference.selector}
        </span>
      ) : null}
    </NodeViewWrapper>
  );
}
