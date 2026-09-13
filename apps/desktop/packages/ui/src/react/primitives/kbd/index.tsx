import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './kbd.css';

export type KbdProps = React.ComponentProps<'kbd'>;

function Kbd({ className, ...props }: KbdProps) {
  return <kbd data-slot="kbd" className={cx(styles.kbd, className)} {...props} />;
}

export type KbdGroupProps = React.ComponentProps<'kbd'>;

function KbdGroup({ className, ...props }: KbdGroupProps) {
  return <kbd data-slot="kbd-group" className={cx(styles.kbdGroup, className)} {...props} />;
}

export { Kbd, KbdGroup };
