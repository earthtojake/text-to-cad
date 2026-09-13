import * as React from 'react';
// Relative import: the dts emitter rewrites aliased imports to a dangling
// relative path, silently degrading the prop types.
import { Textarea, type TextareaProps } from '../../../primitives/textarea';
import { FormFieldShell, type FieldOrientation } from '../field-shell';
import { useFieldContext } from '../form-context';

export interface TextareaFieldProps extends Omit<
  TextareaProps,
  'value' | 'onChange' | 'id' | 'name'
> {
  label?: React.ReactNode;
  description?: React.ReactNode;
  orientation?: FieldOrientation;
  className?: string;
}

export function TextareaField({
  label,
  description,
  orientation,
  className,
  ...textareaProps
}: TextareaFieldProps) {
  const field = useFieldContext<string>();
  return (
    <FormFieldShell
      label={label}
      description={description}
      orientation={orientation}
      className={className}
    >
      {({ id, invalid }) => (
        <Textarea
          id={id}
          name={field.name}
          value={field.state.value ?? ''}
          onBlur={field.handleBlur}
          onChange={(e) => field.handleChange(e.target.value)}
          aria-invalid={invalid || undefined}
          {...textareaProps}
        />
      )}
    </FormFieldShell>
  );
}
