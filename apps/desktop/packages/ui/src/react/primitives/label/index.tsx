import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './label.css';

export type LabelProps = React.ComponentProps<'label'>;

/**
 * Label — standalone form label with the same typography as `Field.Label`.
 *
 * Use `Field.Root` + `Field.Label` when you need automatic control wiring
 * (htmlFor, aria-describedby); use this when labelling something outside a
 * Field, or when wrapping the control as a child.
 */
function Label({ className, ...props }: LabelProps) {
  return <label data-slot="label" className={cx(styles.label, className)} {...props} />;
}

/**
 * MicroLabel — extra-small passive-colored label for dense metadata rows
 * (sidebar group headings, pill captions, toolbar annotations).
 */
function MicroLabel({ className, ...props }: LabelProps) {
  return <label data-slot="micro-label" className={cx(styles.microLabel, className)} {...props} />;
}

export { Label, MicroLabel };
