import { Input as InputPrimitive } from '@base-ui/react/input';
import { inputVariants } from '@styles/recipes/input';
import { cx } from '@styles/utilities/cx';
import * as React from 'react';
// Relative type import: the dts emitter rewrites `@styles/*` type imports to a
// broken relative path, which silently drops the variant props (size, bare)
// from the published InputProps. Keep this one relative until that is fixed.
import type { InputVariantProps } from '../../../styles/recipes/input';

export interface InputProps
  extends Omit<React.ComponentProps<'input'>, 'size'>, InputVariantProps {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, type, size = 'base', bare = false, ...props },
  ref
) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      ref={ref}
      className={cx(inputVariants({ size, bare }), className)}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.currentTarget.blur();
        }
      }}
      {...props}
    />
  );
});

export { Input };
