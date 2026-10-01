import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { formatPromptAnnotation, type PromptReference } from "@text-to-cad/core/prompt";
import { useEffect, useMemo, useRef, useState } from "react";
import { Crosshair, MessageSquareDot, X } from "lucide-react";
import { toast } from "sonner";

import { Popover, PopoverContent, PopoverTrigger } from "@renderer/components/ui/popover";
import { cn } from "@renderer/lib/utils";
import { useExplorer } from "@renderer/state/explorer";
import type { DraftAnnotation } from "@renderer/state/composer";

import type { FileUIPart } from "@renderer/components/ai-elements/types";

import { REFERENCE_CHIP_CLASS, ReferenceChipContent } from "./ReferenceChip";
import type { ReferenceScope } from "./ReferenceScope";

const referencePath = (reference: PromptReference) =>
  reference.resource.kind === "workspace-file" ? reference.resource.path : reference.resource.url;
const referenceSelector = (reference: PromptReference) =>
  reference.target.kind === "cad-selector" ? reference.target.selectors.join(",") : "";

/**
 * Back to where the annotation was made: its model opens, and the viewer opens its card and
 * selects its geometry.
 */
export function openAnnotation(scope: ReferenceScope | null, annotation: DraftAnnotation): void {
  const explorer = useExplorer.getState();
  const file = annotation.references[0] ? referencePath(annotation.references[0]) : "";
  if (!scope || !file || explorer.projectId !== scope.projectId || !explorer.ready) {
    throw new Error("Open this session’s project to see where the annotation is.");
  }
  const tab = explorer.openFile(file, scope.root);
  if (tab) explorer.openCadAnnotation(tab.id, annotation.id);
}

/**
 * The annotations added from the viewer, as one chip in the box's attachment strip: "3 annotations".
 * Pressing the chip opens the list; each note is edited in place there, the way it is edited on
 * the model, and the viewer's copy follows (`heldText` on the destination). A row's crosshair
 * goes back to it on the model, its cross takes it out, and the chip's cross takes them all out.
 * They go out with the prompt when the person sends it (`withAnnotations`).
 *
 * A popover, not a hover card: a note is typed here, and a card that closes when the pointer
 * drifts is no place to type.
 */
export function AnnotationsChip({
  annotations,
  scope,
  onEdit,
  onRemove,
  onRemoveOne,
}: {
  annotations: DraftAnnotation[];
  scope: ReferenceScope | null;
  onEdit: (id: string, text: string) => void;
  onRemove: () => void;
  onRemoveOne: (id: string) => void;
}) {
  if (annotations.length === 0) {
    return null;
  }
  const label = `${annotations.length} ${annotations.length === 1 ? "annotation" : "annotations"}`;
  return (
    <div data-composer-annotations>
      <Popover>
        <span className="inline-flex h-8 max-w-full items-center gap-1.5 rounded-lg border bg-muted/30 pr-1 pl-2 text-[12px]">
          <PopoverTrigger asChild>
            <button
              aria-label={`Edit ${label}`}
              className="inline-flex min-w-0 items-center gap-1.5 rounded-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              type="button"
            >
              <MessageSquareDot aria-hidden className="size-3.5 text-muted-foreground" />
              <span className="truncate">{label}</span>
            </button>
          </PopoverTrigger>
          <button
            aria-label={`Remove ${label}`}
            className="flex size-6 items-center justify-center rounded-md opacity-60 hover:bg-muted hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            onClick={onRemove}
            type="button"
          >
            <X className="size-3" />
          </button>
        </span>
        <PopoverContent align="start" className="w-96 p-2" side="top">
          {/* Scrolls past a few rows: a long list must not climb over the transcript. */}
          <ol aria-label="Annotations in this draft" className="flex max-h-[min(50vh,22rem)] flex-col gap-1 overflow-y-auto text-[12px] leading-5">
            {annotations.map((annotation, index) => (
              <AnnotationRow
                annotation={annotation}
                index={index}
                key={annotation.id}
                onEdit={(text) => onEdit(annotation.id, text)}
                onLocate={() => {
                  try {
                    openAnnotation(scope, annotation);
                  } catch (error) {
                    toast.error(error instanceof Error ? error.message : String(error));
                  }
                }}
                onRemove={() => onRemoveOne(annotation.id)}
              />
            ))}
          </ol>
        </PopoverContent>
      </Popover>
    </div>
  );
}

/**
 * One annotation: its number, its reference chips, its note — pressed to edit in place — and
 * two small actions. Enter saves, Escape puts the note back, and leaving the box saves what was
 * typed, once; an empty note is not saved, because an annotation with nothing to say is deleted,
 * not blanked.
 */
function AnnotationRow({
  annotation,
  index,
  onEdit,
  onLocate,
  onRemove,
}: {
  annotation: DraftAnnotation;
  index: number;
  onEdit: (text: string) => void;
  onLocate: () => void;
  onRemove: () => void;
}) {
  // The draft exists only while editing; it starts from the note as it is then, so a note that
  // changed elsewhere (the model's card) is what an edit here picks up.
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const box = useRef<HTMLTextAreaElement | null>(null);
  const settled = useRef(false);
  useEffect(() => {
    const element = box.current;
    if (!editing || !element) return;
    element.focus();
    element.setSelectionRange(element.value.length, element.value.length);
  }, [editing]);
  const start = () => {
    settled.current = false;
    setDraft(annotation.text);
    setEditing(true);
  };
  const save = () => {
    if (settled.current) return;
    settled.current = true;
    const value = draft.trim();
    if (value) onEdit(value);
    setEditing(false);
  };
  const cancel = () => {
    settled.current = true;
    setEditing(false);
  };
  return (
    <li className="group flex items-start gap-1.5 rounded-md px-1 py-0.5 hover:bg-muted/60" data-annotation-row={annotation.id}>
      <span className="w-4 shrink-0 pt-px text-right text-muted-foreground tabular-nums">{index + 1}.</span>
      {annotation.image ? <SketchThumbnail image={annotation.image} index={index} /> : null}
      <div className="min-w-0 flex-1">
        {annotation.references.map((reference, position) => (
          <span className={cn(REFERENCE_CHIP_CLASS, "mr-1 align-middle")} key={position}>
            <ReferenceChipContent file={referencePath(reference)} label={reference.label} selector={referenceSelector(reference)} />
          </span>
        ))}
        {editing ? (
          <textarea
            aria-label={`Edit annotation ${index + 1}`}
            className="mt-1 w-full resize-none rounded-md border border-input bg-transparent px-2 py-1 text-[12px] leading-5 outline-none focus-visible:ring-1 focus-visible:ring-ring"
            onBlur={save}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              // The composer's own keys (Enter sends, Escape stops a turn) stay out of the note.
              event.stopPropagation();
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                save();
              } else if (event.key === "Escape") {
                event.preventDefault();
                cancel();
              }
            }}
            ref={box}
            rows={2}
            value={draft}
          />
        ) : (
          <TooltipHint content="Edit">
            <button
              aria-label={`Edit annotation ${index + 1}`}
              className={cn(
                "rounded-sm text-left break-words whitespace-pre-wrap hover:underline hover:decoration-muted-foreground/50 hover:underline-offset-2 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                !annotation.text && "text-muted-foreground italic",
              )}
              onClick={start}
              type="button"
            >
              {annotation.text || "Add a note"}
            </button>
          </TooltipHint>
        )}
      </div>
      <span className="flex shrink-0 items-center gap-0.5 opacity-0 group-focus-within:opacity-100 group-hover:opacity-100">
        <TooltipHint content="Show on the model">
          <button
            aria-label={`Show annotation ${index + 1} on the model`}
            className="flex size-6 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            onClick={onLocate}
            type="button"
          >
            <Crosshair className="size-3.5" />
          </button>
        </TooltipHint>
        <TooltipHint content="Remove">
          <button
            aria-label={`Remove annotation ${index + 1}`}
            className="flex size-6 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            onClick={onRemove}
            type="button"
          >
            <X className="size-3.5" />
          </button>
        </TooltipHint>
      </span>
    </li>
  );
}

/** The sketch a note was made over, beside it as a small square: enough to tell which sketch. */
function SketchThumbnail({ image, index }: { image: File; index: number }) {
  // One object URL per image, released when the image changes or the row goes.
  const url = useMemo(() => URL.createObjectURL(image), [image]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  return url ? (
    <TooltipHint content={image.name} side="top">
      <img
        alt={`Sketch for annotation ${index + 1}`}
        className="mt-0.5 size-12 shrink-0 rounded-md border bg-muted/40 object-cover"
        data-annotation-sketch
        src={url}
      />
    </TooltipHint>
  ) : null;
}

/**
 * The prompt with its annotations after it, as a numbered list the agent reads as geometry plus
 * what to do there — and, for a note on a sketch, the name of the picture that goes with it:
 *
 *   Make these changes.
 *
 *   Annotations:
 *   1. bracket.step#o1.1.e3 (Edge 3): make a hole in it
 *   2. bracket.step (Drawing): round this corner [sketch: bracket-drawing.png]
 */
export function withAnnotations(text: string, annotations: readonly DraftAnnotation[]): string {
  if (annotations.length === 0) {
    return text;
  }
  const lines = annotations.map((annotation, index) =>
    `${index + 1}. ${formatPromptAnnotation(annotation, { labels: true })}${annotation.image ? ` [sketch: ${annotation.image.name}]` : ""}`);
  return [text, ["Annotations:", ...lines].join("\n")].filter(Boolean).join("\n\n");
}

/**
 * The sketches of the draft's annotations as the form's file parts, in the annotations' order,
 * so `toPromptBlocks` reads them the way it reads a pasted image. A data URL, read here: the
 * renderer's origin cannot fetch a blob URL (`composer/attachments.ts`).
 */
export async function annotationImageParts(annotations: readonly DraftAnnotation[]): Promise<FileUIPart[]> {
  const parts: FileUIPart[] = [];
  for (const annotation of annotations) {
    if (!annotation.image) continue;
    const url = await new Promise<string | null>((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(typeof reader.result === "string" ? reader.result : null);
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(annotation.image!);
    });
    if (url) parts.push({ type: "file", filename: annotation.image.name, mediaType: annotation.image.type, url });
  }
  return parts;
}
