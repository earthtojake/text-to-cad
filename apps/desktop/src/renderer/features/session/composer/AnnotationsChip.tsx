import { Hash, MessageSquareText, X } from "lucide-react";
import { toast } from "sonner";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@renderer/components/ui/hover-card";
import { parseReference } from "@renderer/features/session/composer/references";
import {
  openComposerReference,
  type ReferenceScope,
} from "@renderer/features/session/composer/ReferenceScope";
import type { DraftAnnotation } from "@renderer/state/composer";

/**
 * Back to where the annotation was made: its model opens, its geometry is selected and its card
 * opens on the model, ready to edit.
 */
export function openAnnotation(
  scope: ReferenceScope | null,
  annotation: DraftAnnotation,
): void {
  const references = annotation.references
    .map((reference) => parseReference(reference.text))
    .filter((reference) => reference !== null);
  const first = references[0];
  if (!scope || !first) {
    throw new Error("Open this chat’s project to see where the annotation is.");
  }
  openComposerReference(
    scope,
    {
      file: first.file,
      selector: references
        .map((reference) => reference.selector)
        .filter(Boolean)
        .join(","),
    },
    { annotation: annotation.id },
  );
}

/**
 * The annotations added from the viewer, as one chip above the box: "3 annotations". Hovering
 * lists them, and pressing one goes back to it on the model; the cross takes them all back out of
 * the draft. They go out with the prompt when the person sends it (`withAnnotations`).
 */
export function AnnotationsChip({
  annotations,
  scope,
  onRemove,
}: {
  annotations: DraftAnnotation[];
  scope: ReferenceScope | null;
  onRemove: () => void;
}) {
  if (annotations.length === 0) {
    return null;
  }
  const label = `${annotations.length} ${annotations.length === 1 ? "annotation" : "annotations"}`;
  return (
    <div className="px-2 pt-2" data-composer-annotations>
      <HoverCard closeDelay={100} openDelay={150}>
        <HoverCardTrigger asChild>
          <span className="inline-flex h-8 max-w-full cursor-default items-center gap-1.5 rounded-lg border bg-muted/30 pr-1 pl-2 text-[12px]">
            <MessageSquareText
              aria-hidden
              className="size-3.5 text-muted-foreground"
            />
            <span className="truncate">{label}</span>
            <button
              aria-label={`Remove ${label}`}
              className="flex size-6 items-center justify-center rounded-md opacity-60 hover:bg-muted hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              onClick={onRemove}
              type="button"
            >
              <X className="size-3" />
            </button>
          </span>
        </HoverCardTrigger>
        <HoverCardContent align="start" className="w-80 p-2" side="top">
          <ol
            aria-label="Annotations in this draft"
            className="flex flex-col gap-1.5 text-[12px] leading-5"
          >
            {annotations.map((annotation, index) => (
              <li key={annotation.id}>
                <button
                  aria-label={`Show annotation ${index + 1} on the model`}
                  className="flex w-full gap-1.5 rounded-md px-1 py-0.5 text-left hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  onClick={() => {
                    try {
                      openAnnotation(scope, annotation);
                    } catch (error) {
                      toast.error(
                        error instanceof Error ? error.message : String(error),
                      );
                    }
                  }}
                  type="button"
                >
                  <span className="w-4 shrink-0 text-right text-muted-foreground tabular-nums">
                    {index + 1}.
                  </span>
                  <span className="min-w-0">
                    {annotation.references.map((reference) => (
                      <span
                        className="mr-1 inline-flex max-w-full items-center gap-0.5 rounded-md border bg-secondary/70 px-1 align-middle text-[11px]"
                        key={reference.text}
                        title={reference.text}
                      >
                        <Hash
                          aria-hidden
                          className="size-2.5 shrink-0 text-muted-foreground"
                        />
                        <span className="truncate">
                          {reference.label ?? reference.text}
                        </span>
                      </span>
                    ))}
                    <span className="break-words">{annotation.text}</span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </HoverCardContent>
      </HoverCard>
    </div>
  );
}

/**
 * The prompt with its annotations after it, as a numbered list the agent reads as geometry
 * plus what to do there:
 *
 *   Make these changes.
 *
 *   Annotations:
 *   1. bracket.step#o1.1.e3 (Edge 3): make a hole in it
 */
export function withAnnotations(
  text: string,
  annotations: DraftAnnotation[],
): string {
  if (annotations.length === 0) {
    return text;
  }
  const lines = annotations.map((annotation, index) => {
    const references = annotation.references
      .map((reference) =>
        reference.label
          ? `${reference.text} (${reference.label})`
          : reference.text,
      )
      .join(" ");
    return `${index + 1}. ${references}${annotation.text ? `: ${annotation.text}` : ""}`;
  });
  return [text, ["Annotations:", ...lines].join("\n")]
    .filter(Boolean)
    .join("\n\n");
}
