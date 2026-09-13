import { Radio as RadioPrimitive } from '@base-ui/react/radio';
import { RadioGroup as RadioGroupPrimitive } from '@base-ui/react/radio-group';
import { cx } from '@styles/utilities/cx';
import * as styles from './radio-group.css';

function RadioGroupRoot({ className, ...props }: RadioGroupPrimitive.Props) {
  return (
    <RadioGroupPrimitive
      data-slot="radio-group"
      className={cx(styles.radioGroup, className)}
      {...props}
    />
  );
}

function RadioGroupItem({ className, ...props }: RadioPrimitive.Root.Props) {
  return (
    <RadioPrimitive.Root
      data-slot="radio-group-item"
      className={cx(styles.radioItem, className)}
      {...props}
    >
      <RadioPrimitive.Indicator data-slot="radio-group-indicator" className={styles.radioIndicator}>
        <span className={styles.radioIndicatorDot} />
      </RadioPrimitive.Indicator>
    </RadioPrimitive.Root>
  );
}

export const RadioGroup = {
  Root: RadioGroupRoot,
  Item: RadioGroupItem,
};
