import { Toggle as TogglePrimitive } from '@base-ui/react/toggle';
import { ToggleGroup as ToggleGroupPrimitive } from '@base-ui/react/toggle-group';
import { controlVariants } from '@styles/recipes/control';
import { cx } from '@styles/utilities/cx';
import * as React from 'react';
// Relative type import: the dts emitter rewrites `@styles/*` type imports to a
// dangling relative path, silently degrading the variant prop types.
import type { ControlVariantProps } from '../../../styles/recipes/control';
import { toggleGroup as toggleGroupClass } from './toggle.css';

// ── Toggle ────────────────────────────────────────────────────────────────────

export interface ToggleProps extends TogglePrimitive.Props {
  size?: ControlVariantProps['size'];
  tone?: ControlVariantProps['tone'];
  icon?: boolean;
}

export const Toggle = React.forwardRef<HTMLButtonElement, ToggleProps>(function Toggle(
  { className, size = 'base', tone = 'neutral', icon = false, ...props },
  ref
) {
  return (
    <TogglePrimitive
      ref={ref}
      data-slot="toggle"
      className={cx(controlVariants({ variant: 'ghost', tone, size, icon }), className)}
      {...props}
    />
  );
});

// ── ToggleGroup ───────────────────────────────────────────────────────────────

export interface ToggleGroupProps extends ToggleGroupPrimitive.Props {
  size?: ControlVariantProps['size'];
  tone?: ControlVariantProps['tone'];
}

function ToggleGroupRoot({ className, ...props }: ToggleGroupProps) {
  return (
    <ToggleGroupPrimitive
      data-slot="toggle-group"
      className={cx(toggleGroupClass, className)}
      {...props}
    />
  );
}

const ToggleGroupItem = React.forwardRef<
  HTMLButtonElement,
  TogglePrimitive.Props & {
    size?: ControlVariantProps['size'];
    tone?: ControlVariantProps['tone'];
    icon?: boolean;
  }
>(function ToggleGroupItem(
  { className, size = 'xs', tone = 'neutral', icon = false, ...props },
  ref
) {
  return (
    <TogglePrimitive
      ref={ref}
      data-slot="toggle-group-item"
      className={cx(controlVariants({ variant: 'ghost', tone, size, icon }), className)}
      {...props}
    />
  );
});

export const ToggleGroup = {
  Root: ToggleGroupRoot,
  Item: ToggleGroupItem,
};
