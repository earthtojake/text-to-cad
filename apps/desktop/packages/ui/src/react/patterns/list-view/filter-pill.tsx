import { cx } from '@styles/utilities/cx';
import { XIcon } from 'lucide-react';
import * as React from 'react';
import * as styles from './filter-pill.css';

// ── FilterPill ────────────────────────────────────────────────────────────────

export interface FilterPillProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Label text shown inside the pill. */
  label: string;
  /** Optional avatar image src to prefix the label. */
  avatarSrc?: string;
  /** Optional color swatch to prefix the label. */
  swatchColor?: string;
  /** Callback fired when the "×" remove button is clicked. */
  onRemove?: () => void;
  /** Accessible label for the remove button. */
  removeLabel?: string;
}

/**
 * ListView.FilterPill — a chip representing one active filter.
 *
 * Supports an optional avatar or color swatch prefix and a "×" remove button.
 */
function FilterPill({
  label,
  avatarSrc,
  swatchColor,
  onRemove,
  removeLabel = 'Remove filter',
  className,
  ...props
}: FilterPillProps) {
  return (
    <span className={cx(styles.pill, className)} {...props}>
      {avatarSrc && <img src={avatarSrc} alt="" className={styles.pillAvatar} aria-hidden />}
      {swatchColor && (
        <span className={styles.pillSwatch} style={{ backgroundColor: swatchColor }} aria-hidden />
      )}
      {label}
      {onRemove && (
        <button
          type="button"
          className={styles.pillRemove}
          onClick={onRemove}
          aria-label={removeLabel}
        >
          <XIcon aria-hidden />
        </button>
      )}
    </span>
  );
}

// ── FilterButton ──────────────────────────────────────────────────────────────

export interface FilterButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Whether this filter is currently active (bold + foreground colour). */
  active?: boolean;
  /** Icon node to show before the label. */
  icon?: React.ReactNode;
}

/**
 * ListView.FilterButton — ghost trigger button for opening a filter popover.
 *
 * Visually equivalent to a ghost link — low-profile until it is active or hovered.
 */
function FilterButton({ active = false, icon, children, className, ...props }: FilterButtonProps) {
  return (
    <button
      type="button"
      data-active={active || undefined}
      className={cx(styles.filterButton, className)}
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}

export { FilterPill, FilterButton };
