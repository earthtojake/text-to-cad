import { LoaderCircle } from 'lucide-react';
import type { FileActivity } from '@hardcore/ui/file-viewer';

/** The original browser filename indicator; the overlay carries the detail. */
export default function FilenameLoadStatus({ activity }: { activity: FileActivity | null }) {
  if (!activity?.loading) return null;
  const label = String(activity.label || '').trim();
  const title = String(activity.title || label || 'Loading').trim();
  return <span role="status" aria-live="polite" title={title} className="ml-1 inline-flex shrink-0 items-center">
    <LoaderCircle className="size-3 shrink-0 animate-spin text-muted-foreground" aria-hidden="true" />
    <span className="sr-only">{title}</span>
  </span>;
}
