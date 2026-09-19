import { LoaderCircle } from 'lucide-react';
import type { FileActivity } from '@hardcore/ui/file-viewer';
export default function FilenameLoadStatus({ activity }: { activity: FileActivity | null }) {
  if (!activity) return null;
  const title=activity.title || activity.label || 'Loading';
  const content=<>{activity.loading ? <LoaderCircle className="size-3 shrink-0 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}<span>{activity.label}</span></>;
  const className=`ml-1 inline-flex shrink-0 items-center gap-1 text-xs ${activity.tone==='error' ? 'text-destructive' : activity.tone==='warning' ? 'text-warning-foreground' : 'text-muted-foreground'}`;
  return activity.onActivate ? <button type="button" title={title} className={className} onClick={activity.onActivate} data-file-status={activity.label}>{content}</button> : <span role="status" aria-live="polite" title={title} className={className} data-file-status={activity.label}>{content}</span>;
}
