import { controlVariants } from '@styles/recipes/control';
import { cx } from '@styles/utilities/cx';
import { ChevronDownIcon } from 'lucide-react';
import * as React from 'react';
// Relative type import: the dts emitter rewrites `@styles/*` type imports to a
// dangling relative path, silently degrading the variant prop types.
import type { ControlVariantProps } from '../../../styles/recipes/control';
import {
  triggerButtonChevron,
  triggerButtonExtra,
  triggerInputLayoutBase,
  triggerInputLayoutSm,
} from './trigger-button.css';
import { fieldShellBase } from '@styles/recipes/field-shell.css';

export interface TriggerButtonProps
  extends
    React.ButtonHTMLAttributes<HTMLButtonElement>,
    Pick<ControlVariantProps, 'size' | 'tone'> {
  /**
   * Show a trailing chevron icon (for selects, comboboxes, dropdowns).
   * @default true
   */
  showChevron?: boolean;
  /**
   * Visual appearance of the trigger.
   * - `control` (default): ghost button style — transparent background, no border.
   * - `input`: matches Input/Textarea — border, `surfaceInput` background, focus ring.
   */
  appearance?: 'control' | 'input';
}

/**
 * TriggerButton — a ghost control that opens an overlay and reads as "active"
 * while the overlay is open.
 *
 * Used as the trigger face for Select, Combobox, DropdownMenu, and Popover.
 * When wired via base-ui's `render` prop, the primitive sets `aria-expanded`
 * and/or `data-popup-open` automatically, which the controlVariants recipe
 * maps to bg-surface-selected (active state) with no extra rules.
 *
 * Pass `appearance="input"` in form contexts so the trigger visually matches
 * Input and Textarea controls (same border, background, focus ring, invalid ring).
 */
const TriggerButton = React.forwardRef<HTMLButtonElement, TriggerButtonProps>(
  function TriggerButton(
    {
      className,
      size = 'base',
      tone = 'neutral',
      showChevron = true,
      appearance = 'control',
      children,
      ...props
    },
    ref
  ) {
    const buttonClass =
      appearance === 'input'
        ? cx(
            fieldShellBase,
            triggerInputLayoutBase,
            size === 'xs' && triggerInputLayoutSm,
            className
          )
        : cx(controlVariants({ variant: 'ghost', tone, size }), triggerButtonExtra, className);

    return (
      <button ref={ref} type="button" data-slot="trigger-button" className={buttonClass} {...props}>
        {children}
        {showChevron && (
          <ChevronDownIcon size={14} strokeWidth={1} className={triggerButtonChevron} aria-hidden />
        )}
      </button>
    );
  }
);

export { TriggerButton };
