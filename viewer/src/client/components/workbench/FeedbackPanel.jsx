import { useCallback, useEffect, useState } from "react";

import { fetchFeedback, submitFeedback } from "../../workbench/cadManifestStore";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { ScrollArea } from "../ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "../ui/sheet";
import { Switch } from "../ui/switch";
import { Textarea } from "../ui/textarea";

const FEEDBACK_REFERENCE_FIELDS = [
  "id",
  "label",
  "summary",
  "copyText",
  "partId",
  "entityType",
  "selectorType",
  "displaySelector",
];

function pickReferenceFields(reference) {
  const picked = {};
  for (const field of FEEDBACK_REFERENCE_FIELDS) {
    const value = String(reference?.[field] || "").trim();
    if (value) {
      picked[field] = value;
    }
  }
  return picked;
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error || new Error("Failed to read screenshot"));
    reader.readAsDataURL(blob);
  });
}

export default function FeedbackPanel({
  open,
  onOpenChange,
  selectedReferences = [],
  drawingStrokes = [],
  getPerspective,
  captureScreenshotBlob,
}) {
  const [comment, setComment] = useState("");
  const [includeScreenshot, setIncludeScreenshot] = useState(true);
  const [includeAnnotations, setIncludeAnnotations] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [items, setItems] = useState([]);

  const refreshItems = useCallback(async () => {
    try {
      setItems(await fetchFeedback());
    } catch {
      // Listing is best-effort; submission errors surface separately.
    }
  }, []);

  useEffect(() => {
    if (open) {
      setError("");
      refreshItems();
    }
  }, [open, refreshItems]);

  const trimmedComment = comment.trim();
  const hasStrokes = Array.isArray(drawingStrokes) && drawingStrokes.length > 0;

  const handleSubmit = useCallback(async () => {
    if (!trimmedComment || submitting) {
      return;
    }
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      let screenshotBase64 = "";
      let screenshotMissing = false;
      if (includeScreenshot && typeof captureScreenshotBlob === "function") {
        try {
          const blob = await captureScreenshotBlob();
          if (blob) {
            screenshotBase64 = await blobToBase64(blob);
          } else {
            screenshotMissing = true;
          }
        } catch {
          // Screenshot is optional context; keep the comment + references.
          screenshotMissing = true;
        }
      }
      let camera = null;
      if (typeof getPerspective === "function") {
        try {
          camera = getPerspective() || null;
        } catch {
          camera = null;
        }
      }
      await submitFeedback({
        comment: trimmedComment,
        references: selectedReferences.map(pickReferenceFields),
        camera,
        drawingStrokes: includeAnnotations && hasStrokes ? drawingStrokes : [],
        screenshotBase64,
      });
      setComment("");
      setNotice(screenshotMissing ? "Submitted — no screenshot could be captured for this view." : "");
      await refreshItems();
    } catch (submitError) {
      setError(submitError?.message || "Failed to submit feedback");
    } finally {
      setSubmitting(false);
    }
  }, [
    captureScreenshotBlob,
    drawingStrokes,
    getPerspective,
    hasStrokes,
    includeAnnotations,
    includeScreenshot,
    refreshItems,
    selectedReferences,
    submitting,
    trimmedComment,
  ]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Feedback</SheetTitle>
          <SheetDescription>
            Describe what is wrong with the current selection. Saved next to the model for the agent to read.
          </SheetDescription>
        </SheetHeader>

        <div className="flex min-h-0 flex-1 flex-col gap-4 px-4">
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">
              {selectedReferences.length
                ? `Selected (${selectedReferences.length})`
                : "No selection — comment applies to the whole model"}
            </span>
            {selectedReferences.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {selectedReferences.map((reference) => (
                  <Badge key={reference.id} variant="secondary">
                    {reference.label || reference.copyText || reference.id}
                  </Badge>
                ))}
              </div>
            )}
          </div>

          <Textarea
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            placeholder="e.g. this fillet is too sharp, the hole should be 6mm…"
            rows={4}
            autoFocus
          />

          <label className="flex items-center justify-between gap-3 text-sm">
            <span>Attach screenshot</span>
            <Switch checked={includeScreenshot} onCheckedChange={setIncludeScreenshot} />
          </label>
          <label className="flex items-center justify-between gap-3 text-sm">
            <span>
              Include annotations{hasStrokes ? ` (${drawingStrokes.length})` : ""}
            </span>
            <Switch
              checked={includeAnnotations && hasStrokes}
              onCheckedChange={setIncludeAnnotations}
              disabled={!hasStrokes}
            />
          </label>

          {error && <p className="text-sm text-destructive">{error}</p>}
          {notice && <p className="text-sm text-muted-foreground">{notice}</p>}

          {items.length > 0 && (
            <div className="flex min-h-0 flex-1 flex-col gap-1.5">
              <span className="text-xs font-medium text-muted-foreground">
                Previous feedback ({items.length})
              </span>
              <ScrollArea className="min-h-0 flex-1 rounded-md border">
                <ul className="flex flex-col divide-y">
                  {items.map((item) => (
                    <li key={item.id} className="flex flex-col gap-1 p-2 text-sm">
                      <span className="font-medium">{item.comment}</span>
                      {Array.isArray(item.references) && item.references.length > 0 && (
                        <span className="text-xs text-muted-foreground">
                          {item.references.map((reference) => reference.label || reference.copyText || reference.id).join(", ")}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </ScrollArea>
            </div>
          )}
        </div>

        <SheetFooter>
          <Button onClick={handleSubmit} disabled={!trimmedComment || submitting}>
            {submitting ? "Submitting…" : "Submit feedback"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
