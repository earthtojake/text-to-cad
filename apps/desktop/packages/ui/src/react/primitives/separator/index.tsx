import { Separator as SeparatorPrimitive } from '@base-ui/react/separator';
import { cx } from '@styles/utilities/cx';
import * as styles from './separator.css';

export interface SeparatorProps extends Omit<SeparatorPrimitive.Props, 'className'> {
  className?: string;
}

/**
 * Separator — 1px hairline divider. Horizontal fills the row width; vertical
 * stretches to the height of its flex container.
 */
function Separator({ className, orientation = 'horizontal', ...props }: SeparatorProps) {
  return (
    <SeparatorPrimitive
      data-slot="separator"
      orientation={orientation}
      className={cx(styles.separator, className)}
      {...props}
    />
  );
}

export { Separator };
