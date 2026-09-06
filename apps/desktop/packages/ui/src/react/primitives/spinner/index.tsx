import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './spinner.css';

export type SpinnerSize = 'sm' | 'md' | 'lg';

export interface SpinnerProps extends React.SVGProps<SVGSVGElement> {
  size?: SpinnerSize;
}

/**
 * Spinner — plain circular activity indicator (rotating arc over a faint
 * track). Inherits color via `currentColor`.
 *
 * For the calmer 8-segment radial indicator use `SegmentedSpinnerIcon`.
 */
const Spinner = React.forwardRef<SVGSVGElement, SpinnerProps>(function Spinner(
  { className, size = 'md', ...props },
  ref
) {
  return (
    <svg
      ref={ref}
      className={cx(styles.spinner, styles.size[size], className)}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
      {...props}
    >
      <circle
        className={styles.track}
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className={styles.arc}
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
});

export { Spinner };
