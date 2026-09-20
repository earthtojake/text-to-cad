import { useEffect, useRef } from 'react';

// A tooltip that counts loaded components changes with every component; the
// status beside the filename does not. A few host renders a second keep the
// count readable without re-rendering the whole FileViewer per component.
export const ACTIVITY_DETAIL_INTERVAL_MS = 250;

const sameStatus = (left, right) => Boolean(left && right) && left.loading === right.loading &&
  left.label === right.label && left.tone === right.tone && Boolean(left.onActivate) === Boolean(right.onActivate);

/**
 * Publish this file's `FileActivity` to the host.
 *
 * A status change — busy, label, tone, actionable — reaches the host in the
 * commit that made it. A change of `title` alone is progress detail: it is
 * coalesced onto a timer, latest value wins. Publishing each one from the
 * effect made every progress commit schedule a host update from its passive
 * effects, one full FileViewer render per loaded component, and a large
 * assembly tripped React's nested-update limit doing it.
 */
export function useFileActivityReport(activity, onActivityChange, intervalMs = ACTIVITY_DETAIL_INTERVAL_MS) {
  const latest = useRef(activity), published = useRef(null), timer = useRef(0);
  useEffect(() => {
    latest.current = activity;
    if (sameStatus(published.current, activity)) {
      if (published.current.title !== activity.title && !timer.current) timer.current = setTimeout(() => {
        timer.current = 0;
        published.current = latest.current;
        onActivityChange?.(latest.current);
      }, intervalMs);
      return;
    }
    clearTimeout(timer.current);
    timer.current = 0;
    published.current = activity;
    onActivityChange?.(activity);
  }, [activity, onActivityChange, intervalMs]);
  useEffect(() => () => {
    clearTimeout(timer.current);
    timer.current = 0;
    published.current = null;
    onActivityChange?.(null);
  }, [onActivityChange]);
}
