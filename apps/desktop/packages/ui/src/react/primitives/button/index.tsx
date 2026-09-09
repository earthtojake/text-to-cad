import { Button as ButtonPrimitive } from '@base-ui/react/button';
import { controlVariants } from '@styles/recipes/control';
import { cx } from '@styles/utilities/cx';
import * as React from 'react';
// Relative type import: the dts emitter rewrites `@styles/*` type imports to a
// broken relative path, silently degrading the variant prop types. Keep this
// relative until that is fixed.
import type { ControlVariantProps } from '../../../styles/recipes/control';
import * as buttonStyles from './button.css';

export type ButtonVariant = NonNullable<ControlVariantProps['variant']> | 'destructive' | 'link';

export type ButtonProps = ButtonPrimitive.Props &
  Omit<ControlVariantProps, 'variant' | 'kbd'> & {
    variant?: ButtonVariant;
    /** Square aspect ratio; collapses padding. Combines with size. */
    icon?: boolean;
    /** Trailing keyboard shortcut; reduces right padding so the Kbd aligns. */
    kbd?: React.ReactNode;
  };

export function resolveButtonControlVariant({
  variant,
  tone,
  size,
}: {
  variant: ButtonVariant;
  tone: ControlVariantProps['tone'];
  size: ControlVariantProps['size'];
}): ControlVariantProps {
  if (variant === 'destructive') {
    return { variant: 'primary', tone: 'destructive', size };
  }

  if (variant === 'link') {
    return { variant: 'ghost', tone, size: 'link' };
  }

  return { variant, tone, size };
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    className,
    variant = 'ghost',
    tone = 'neutral',
    size = 'base',
    icon = false,
    kbd,
    children,
    ...props
  },
  ref
) {
  const controlVariant = resolveButtonControlVariant({ variant, tone, size });

  return (
    <ButtonPrimitive
      ref={ref}
      data-slot="button"
      data-variant={controlVariant.variant}
      data-tone={controlVariant.tone}
      data-kbd={kbd ? '' : undefined}
      className={cx(
        controlVariants({ ...controlVariant, icon, kbd: Boolean(kbd) }),
        buttonStyles.kbdHost,
        className
      )}
      {...props}
    >
      {children}
      {kbd}
    </ButtonPrimitive>
  );
});

export { Button };
