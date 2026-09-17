import { LoaderCircle } from "lucide-react";
import type { FileActivity } from "./types.js";

export default function FileActivityStatus({ activity }: { activity: FileActivity | null }) {
  if (!activity) return null;
  const title = activity.title || activity.label || "Loading";
  const className = `ml-1 inline-flex shrink-0 items-center gap-1 rounded-sm text-tiny ${activity.tone === "error" ? "text-destructive" : activity.tone === "warning" ? "text-warning-foreground" : "text-muted-foreground"}`;
  const content = <>{activity.loading ? <LoaderCircle className="size-3 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}{activity.label ? <span>{activity.label}</span> : null}</>;
  return activity.onActivate ? <button type="button" className={className} title={title} aria-label={activity.label || title} onClick={activity.onActivate} data-file-status={activity.label}>{content}</button>
    : <span role="status" aria-live="polite" className={className} title={title} data-file-status={activity.label}>{content}</span>;
}
