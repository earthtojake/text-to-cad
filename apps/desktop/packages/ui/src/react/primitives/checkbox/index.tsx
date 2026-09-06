import { Checkbox as CheckboxPrimitive } from '@base-ui/react/checkbox';
import { cx } from '@styles/utilities/cx';
import { CheckIcon } from 'lucide-react';
import * as React from 'react';
import * as styles from './checkbox.css';

export interface CheckboxProps extends Omit<CheckboxPrimitive.Root.Props, 'className'> {
  className?: string;
}

/**
 * Checkbox — base-ui checkbox with an enlarged invisible hit target.
 *
 * Inside a disabled `Field.Root` the control inherits base-ui's disabled state
 * (data-disabled) and dims automatically; no wrapper class is needed.
 */
const Checkbox = React.forwardRef<HTMLButtonElement, CheckboxProps>(function Checkbox(
  { className, ...props },
  ref
) {
  return (
    <CheckboxPrimitive.Root
      ref={ref}
      data-slot="checkbox"
      className={cx(styles.root, className)}
      {...props}
    >
      <CheckboxPrimitive.Indicator data-slot="checkbox-indicator" className={styles.indicator}>
        <CheckIcon absoluteStrokeWidth strokeWidth={3} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
});

export { Checkbox };
