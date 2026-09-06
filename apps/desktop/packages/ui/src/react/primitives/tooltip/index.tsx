'use client';

import { Tooltip as TooltipPrimitive } from '@base-ui/react/tooltip';
import { cx } from '@styles/utilities/cx';
import * as styles from './tooltip.css';

/**
 * Shares open delay and warm-up grouping across the tooltips below it: once
 * one tooltip opens, adjacent ones open instantly. Defaults to no delay —
 * mount an app-level provider with a `delay` to get hover-intent behavior.
 */
function TooltipProvider({ delay = 0, ...props }: TooltipPrimitive.Provider.Props) {
  return <TooltipPrimitive.Provider delay={delay} {...props} />;
}

function TooltipRoot({ ...props }: TooltipPrimitive.Root.Props) {
  return <TooltipPrimitive.Root data-slot="tooltip" {...props} />;
}

function TooltipTrigger({ ...props }: TooltipPrimitive.Trigger.Props) {
  return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" {...props} />;
}

function TooltipContent({
  className,
  side = 'top',
  sideOffset = 4,
  align = 'center',
  alignOffset = 0,
  showArrow = true,
  children,
  ...props
}: TooltipPrimitive.Popup.Props &
  Pick<TooltipPrimitive.Positioner.Props, 'align' | 'alignOffset' | 'side' | 'sideOffset'> & {
    showArrow?: boolean;
  }) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Positioner
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
        className={styles.positioner}
      >
        <TooltipPrimitive.Popup
          data-slot="tooltip-content"
          className={cx(styles.content, className)}
          {...props}
        >
          {children}
          {showArrow ? <TooltipPrimitive.Arrow className={styles.arrow} /> : null}
        </TooltipPrimitive.Popup>
      </TooltipPrimitive.Positioner>
    </TooltipPrimitive.Portal>
  );
}

export const Tooltip = {
  Provider: TooltipProvider,
  Root: TooltipRoot,
  Trigger: TooltipTrigger,
  Content: TooltipContent,
};
