import * as React from 'react';
// Relative import: the dts emitter rewrites aliased imports to a dangling
// relative path, silently degrading the prop types.
import { Field, type FieldVariants } from '../../primitives/field';
import { useFieldContext } from './form-context';

export type FieldOrientation = NonNullable<FieldVariants['orientation']>;

export interface FormFieldShellProps {
  label?: React.ReactNode;
  description?: React.ReactNode;
  orientation?: FieldOrientation;
  className?: string;
  children: (wiring: { id: string; invalid: boolean }) => React.ReactNode;
}

/**
 * FormFieldShell — shared layout wrapper used by all typed form field components.
 *
 * Reads field state from `useFieldContext()`, computes the invalid flag, and
 * renders the accessible `Field` primitive with label, description, error, and
 * the control provided via the render-prop `children`.
 *
 * In `vertical` mode (default): label/description stack above the control.
 * In `horizontal` mode: label/description occupy the left side and the control
 * sits on the right — use this for settings-style rows.
 */
export function FormFieldShell({
  label,
  description,
  orientation = 'vertical',
  className,
  children,
}: FormFieldShellProps) {
  const field = useFieldContext();
  const invalid = field.state.meta.isTouched && !field.state.meta.isValid;
  const id = field.name;

  const errors = invalid
    ? field.state.meta.errors
        .map((e) => (typeof e === 'string' ? e : (e as { message?: string })?.message))
        .filter(Boolean)
        .join(', ')
    : null;

  const hasTextContent = label != null || description != null;

  if (orientation === 'horizontal') {
    return (
      <Field.Root orientation="horizontal" className={className}>
        {hasTextContent && (
          <Field.Content>
            {label != null && (
              <Field.Label id={`${id}-label`} htmlFor={id}>
                {label}
              </Field.Label>
            )}
            {description != null && <Field.Description>{description}</Field.Description>}
          </Field.Content>
        )}
        <Field.ControlSlot>{children({ id, invalid })}</Field.ControlSlot>
      </Field.Root>
    );
  }

  return (
    <Field.Root orientation="vertical" className={className}>
      {label != null && (
        <Field.Label id={`${id}-label`} htmlFor={id}>
          {label}
        </Field.Label>
      )}
      {children({ id, invalid })}
      {description != null && <Field.Description>{description}</Field.Description>}
      {errors && <Field.Error>{errors}</Field.Error>}
    </Field.Root>
  );
}
