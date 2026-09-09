import { cx } from '@styles/utilities/cx';
import { SearchIcon, XIcon } from 'lucide-react';
import * as React from 'react';
// Relative type import: the dts emitter rewrites `@styles/*` type imports to a
// dangling relative path, silently degrading the variant prop types.
import type { InputVariantProps } from '../../../styles/recipes/input';
import { Input } from '../input';
import * as styles from './search-input.css';

export interface SearchInputProps extends Omit<React.ComponentProps<'input'>, 'size' | 'type'> {
  size?: InputVariantProps['size'];
  /** Called when the user clicks the × clear button. Renders the button when provided. */
  onClear?: () => void;
  /** Optional trailing content, such as a keyboard shortcut hint. */
  shortcut?: React.ReactNode;
}

/**
 * SearchInput — a text input with a leading search icon and an optional
 * trailing clear button.
 *
 * Delegates to the `Input` primitive for all field-shell styling (border,
 * background, focus ring, invalid ring) and adds left padding to make room
 * for the icon.
 *
 * Usage:
 *   // Uncontrolled, no clear button
 *   <SearchInput placeholder="Search…" />
 *
 *   // Controlled with clear
 *   <SearchInput
 *     value={query}
 *     onChange={(e) => setQuery(e.target.value)}
 *     onClear={() => setQuery('')}
 *     placeholder="Filter tasks…"
 *   />
 */
const SearchInput = React.forwardRef<HTMLInputElement, SearchInputProps>(function SearchInput(
  { className, size = 'base', onClear, shortcut, value, style: consumerStyle, ...props },
  ref
) {
  const hasValue = value !== undefined && value !== '';

  // Left padding: icon (0.875rem) + left offset (0.625rem) + gap (0.25rem) = ~1.875rem → 2rem
  const paddingLeft = size === 'sm' ? '1.75rem' : '2rem';
  // Right padding only reserves space for the clear button; the shortcut is treated as a
  // placeholder overlay and does not reduce the input's available text width.
  const paddingRight = onClear != null ? '1.875rem' : undefined;

  return (
    <div data-slot="search-input" className={styles.container} style={consumerStyle}>
      <span className={styles.icon} aria-hidden>
        <SearchIcon />
      </span>

      <Input
        ref={ref}
        type="search"
        size={size}
        value={value}
        className={cx(className)}
        style={{ paddingLeft, paddingRight }}
        {...props}
      />

      {shortcut != null && (
        <span data-slot="search-input-shortcut" className={cx(styles.shortcut)}>
          {shortcut}
        </span>
      )}

      {onClear != null && hasValue && (
        <button
          type="button"
          aria-label="Clear search"
          className={styles.clearButton}
          tabIndex={-1}
          onClick={onClear}
        >
          <XIcon aria-hidden />
        </button>
      )}
    </div>
  );
});

export { SearchInput };
