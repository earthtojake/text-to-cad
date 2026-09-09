import { NodeViewWrapper, type NodeViewProps } from "@tiptap/react";
import { Box, Hash } from "lucide-react";
import { useContext } from "react";
import { toast } from "sonner";

import { cn } from "@renderer/lib/utils";
import type { CadReference } from "@shared/cad-refs";
import { useComposer } from "@renderer/state/composer";

import { referenceToken } from "./references";
import { openComposerReference, ReferenceScopeContext } from "./ReferenceScope";

/**
 * How a reference looks in the composer: a file icon, the file's name and
 * its part/feature label (or selector badge) — `bracket.step · Mount`.
 * A friendly label never replaces the model name. A bare selector (`#o1.2`,
 * the current file's) shows a hash instead of a file. The whole token is
 * the tooltip, and the chip is what the arrow keys land on; `selected` is
 * ProseMirror's NodeSelection, drawn as a ring so a keyboard user can see
 * what Delete would remove. Clicking the chip reveals its geometry without
 * moving the caret; Tab then Enter activates it without submitting the form.
 */
export function ReferenceChip({ node, selected }: NodeViewProps) {
  const scope = useContext(ReferenceScopeContext);
  const reference = node.attrs as CadReference;
  const name = reference.file ? (reference.file.split(/[\\/]/).pop() ?? reference.file) : "";
  const token = referenceToken(reference);
  const label = useComposer((state) => scope?.draftKey ? state.referenceLabels[scope.draftKey]?.[token] : undefined);
  return (
    <NodeViewWrapper
      as="span"
      className={cn(
        "ui-reference-enter mx-px inline-flex max-w-full rounded-md border bg-secondary/70 align-baseline text-[12px] leading-4 text-secondary-foreground select-none",
        selected && "ring-2 ring-ring ring-offset-1 ring-offset-background",
      )}
      contentEditable={false}
      data-file={reference.file}
      data-reference-chip=""
      data-selected={selected ? "" : undefined}
      data-selector={reference.selector}
      title={scope ? `Show ${token} in viewer` : token}
    >
      <button
        aria-label={`Show ${label ? `${label} (${token})` : token} in viewer`}
        className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-md px-1.5 py-px transition-colors duration-120 hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none"
        disabled={!scope}
        type="button"
        onMouseDown={(event) => event.preventDefault()}
        onKeyDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation();
          if (!scope) return;
          try {
            openComposerReference(scope, reference);
          } catch (error) {
            toast.error(error instanceof Error ? error.message : String(error));
          }
        }}
      >
        {name ? (
          <Box aria-hidden className="size-3 shrink-0 opacity-70" />
        ) : (
          <Hash aria-hidden className="size-3 shrink-0 opacity-70" />
        )}
        {name ? (
          <span className="min-w-0 max-w-[160px] truncate" data-reference-model>{name}</span>
        ) : null}
        {name && label ? <span aria-hidden className="shrink-0 text-muted-foreground"> · </span> : null}
        {label ? (
          <span className="min-w-0 max-w-[160px] truncate text-muted-foreground" data-reference-label title={label}>{label}</span>
        ) : null}
        {!label && reference.selector ? (
          <span className="min-w-0 max-w-[160px] truncate rounded-sm bg-primary/10 px-1 font-mono text-[11px] text-primary" data-selector-badge>
            {reference.selector}
          </span>
        ) : null}
      </button>
    </NodeViewWrapper>
  );
}
