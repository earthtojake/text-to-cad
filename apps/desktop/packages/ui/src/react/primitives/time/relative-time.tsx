import { formatDistanceToNowStrict } from 'date-fns';
import * as React from 'react';
import { parseTimestamp } from './parse-timestamp';
import * as styles from './time.css';

export interface RelativeTimeProps {
  value: string | number | Date;
  className?: string;
  /** Renders an abbreviated form (e.g. "3d", "5mo") instead of the full distance. */
  compact?: boolean;
  /** In compact mode, appends a muted "ago" suffix (skipped while showing "now"). */
  ago?: boolean;
}

/** Abbreviate date-fns distance units; timestamps under a minute old show "now". */
export function toCompactLabel(date: Date, now: number = Date.now()): string {
  if (now - date.getTime() < 60_000) return 'now';
  return formatDistanceToNowStrict(date, { roundingMethod: 'floor', addSuffix: false })
    .replace(/ seconds?/, 's')
    .replace(/ minutes?/, 'm')
    .replace(/ hours?/, 'h')
    .replace(/ days?/, 'd')
    .replace(/ months?/, 'mo')
    .replace(/ years?/, 'y');
}

/**
 * RelativeTime — renders a timestamp as a distance from now ("3 minutes ago"),
 * re-rendering on a 60-second interval so displayed distances stay current.
 * Unparseable input renders "—".
 */
export function RelativeTime({ value, className, compact, ago }: RelativeTimeProps) {
  const [, setTick] = React.useState(0);

  React.useEffect(() => {
    const timer = setInterval(() => setTick((t) => t + 1), 60_000);
    return () => clearInterval(timer);
  }, []);

  const date = React.useMemo(() => parseTimestamp(value), [value]);
  if (!date) {
    return <span className={className}>—</span>;
  }

  if (compact) {
    const short = toCompactLabel(date);
    const showAgo = ago && short !== 'now';

    return (
      <time className={className} dateTime={date.toISOString()}>
        {short}
        {showAgo && <span className={styles.agoSuffix}> ago</span>}
      </time>
    );
  }

  return (
    <time className={className} dateTime={date.toISOString()}>
      {formatDistanceToNowStrict(date, { addSuffix: true })}
    </time>
  );
}
