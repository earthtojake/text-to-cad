import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './braille-spinner.css';

const DOTS_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'] as const;
const WAVE_FRAMES = [
  '⠈',
  '⠉',
  '⠋',
  '⠓',
  '⠒',
  '⠐',
  '⠐',
  '⠒',
  '⠖',
  '⠦',
  '⠤',
  '⠠',
  '⠠',
  '⠤',
  '⠦',
  '⠖',
  '⠒',
  '⠐',
  '⠐',
  '⠒',
  '⠓',
  '⠋',
  '⠉',
  '⠈',
] as const;

const FRAME_INTERVAL_MS = 80;

export type BrailleSpinnerVariant = 'dots' | 'wave';

export interface BrailleSpinnerProps extends Omit<
  React.HTMLAttributes<HTMLSpanElement>,
  'children'
> {
  variant?: BrailleSpinnerVariant;
}

function useBrailleFrame(frames: readonly string[]) {
  const [frameIndex, setFrameIndex] = React.useState(0);

  React.useEffect(() => {
    // Show a static frame instead of cycling when the user opts out of motion.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const interval = setInterval(() => {
      setFrameIndex((index) => (index + 1) % frames.length);
    }, FRAME_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [frames]);

  return frames[frameIndex % frames.length];
}

/**
 * Terminal-style braille-frame text spinner. Inherits the ambient font size,
 * so size it through the surrounding text context (AgentStatus sizes it via
 * its bounding box).
 */
function BrailleSpinner({ variant = 'dots', className, ...props }: BrailleSpinnerProps) {
  const frame = useBrailleFrame(variant === 'wave' ? WAVE_FRAMES : DOTS_FRAMES);

  return (
    <span aria-hidden="true" {...props} className={cx(styles.spinner, className)}>
      {frame}
    </span>
  );
}

export { BrailleSpinner };
