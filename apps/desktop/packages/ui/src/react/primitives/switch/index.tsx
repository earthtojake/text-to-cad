import { Switch as SwitchPrimitive } from '@base-ui/react/switch';
import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './switch.css';
import type { SwitchVariants } from './switch.css';

export interface SwitchProps extends Omit<SwitchPrimitive.Root.Props, 'className'> {
  className?: string;
  size?: SwitchVariants['size'];
}

const Switch = React.forwardRef<HTMLSpanElement, SwitchProps>(function Switch(
  { className, size = 'base', onKeyDown, ...props },
  ref
) {
  return (
    <SwitchPrimitive.Root
      ref={ref}
      data-slot="switch"
      data-size={size}
      className={cx(styles.switchRoot({ size }), className)}
      onKeyDown={(event) => {
        // The global `app.confirm` keybinding uses modifier+Enter; keep a focused
        // switch from also toggling on the same press (base-ui ignores
        // defaultPrevented, so its handler must be suppressed explicitly).
        if (
          (event.metaKey || event.ctrlKey || event.altKey) &&
          (event.key === 'Enter' || event.key === ' ')
        ) {
          event.preventBaseUIHandler?.();
        }
        onKeyDown?.(event);
      }}
      {...props}
    >
      <SwitchPrimitive.Thumb className={styles.switchThumb} />
    </SwitchPrimitive.Root>
  );
});

export { Switch };
