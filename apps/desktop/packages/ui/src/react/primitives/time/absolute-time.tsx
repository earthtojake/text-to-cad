import { format } from 'date-fns';
import * as React from 'react';
import { parseTimestamp } from './parse-timestamp';

export interface AbsoluteTimeProps {
  value: string | number | Date;
  className?: string;
  /** When true, includes the year regardless of recency. */
  includeYear?: boolean;
}

/**
 * AbsoluteTime — renders a timestamp as a fixed calendar date/time
 * (e.g. "Mar 4, 16:20"), automatically including the year when the
 * date falls outside the current year. Unparseable input renders "—".
 */
export function AbsoluteTime({ value, className, includeYear }: AbsoluteTimeProps) {
  const date = React.useMemo(() => parseTimestamp(value), [value]);
  if (!date) return <span className={className}>—</span>;

  const showYear = includeYear || date.getFullYear() !== new Date().getFullYear();
  const pattern = showYear ? 'MMM d yyyy, HH:mm' : 'MMM d, HH:mm';

  return (
    <time className={className} dateTime={date.toISOString()}>
      {format(date, pattern)}
    </time>
  );
}
