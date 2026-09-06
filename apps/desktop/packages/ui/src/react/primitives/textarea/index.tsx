import { inputVariants } from '@styles/recipes/input';
import { cx } from '@styles/utilities/cx';
import * as React from 'react';
// Relative type import: the dts emitter rewrites `@styles/*` type imports to a
// dangling relative path, silently degrading the variant prop types.
import type { InputVariantProps } from '../../../styles/recipes/input';
import { textareaOverride } from './textarea.css';

export interface TextareaProps extends React.ComponentProps<'textarea'> {
  /** Match the visual size token from inputVariants (height constraint is dropped for auto-grow). */
  size?: InputVariantProps['size'];
}

function Textarea({ className, size = 'base', ...props }: TextareaProps) {
  return (
    <textarea
      data-slot="textarea"
      className={cx(inputVariants({ size }), textareaOverride, className)}
      {...props}
    />
  );
}

export { Textarea };
