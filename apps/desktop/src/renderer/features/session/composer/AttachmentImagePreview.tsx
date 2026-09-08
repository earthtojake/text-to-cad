import { Expand } from "lucide-react";

import { AttachmentPreview } from "@renderer/components/ai-elements/attachments";
import type { FileUIPart } from "@renderer/components/ai-elements/types";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@renderer/components/ui/dialog";

/** Inspect the original attachment; opening a preview never submits the draft. */
export function AttachmentImagePreview({ file }: { file: FileUIPart }) {
  const name = file.filename || "Attached image";
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          aria-label={`Enlarge ${name}`}
          className="ui-preview-trigger group/preview relative shrink-0 cursor-zoom-in rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          title="Click to enlarge"
          type="button"
        >
          <AttachmentPreview className="size-16 rounded-md border bg-background [&_img]:object-contain" />
          <span className="pointer-events-none absolute right-1 bottom-1 rounded bg-background/90 p-0.5 opacity-0 transition-opacity group-hover/preview:opacity-100 group-focus-visible/preview:opacity-100" aria-hidden>
            <Expand className="size-3" />
          </span>
        </button>
      </DialogTrigger>
      <DialogContent
        aria-describedby={undefined}
        className="ui-image-preview flex max-h-[calc(100dvh-2rem)] w-[min(960px,calc(100vw-2rem))] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none"
        onEscapeKeyDown={(event) => event.stopPropagation()}
        onKeyDown={(event) => event.stopPropagation()}
      >
        <div className="shrink-0 border-b px-4 py-4 pr-12">
          <DialogTitle className="truncate text-sm font-medium" title={name}>{name}</DialogTitle>
        </div>
        <div className="flex min-h-0 items-center justify-center bg-muted/20 p-3">
          <img alt={name} className="max-h-[calc(100dvh-7rem)] max-w-full object-contain" src={file.url} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
