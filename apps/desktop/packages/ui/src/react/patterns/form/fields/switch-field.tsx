import { Switch } from '@react/primitives/switch';
import * as React from 'react';
import { FormFieldShell, type FieldOrientation } from '../field-shell';
import { useFieldContext } from '../form-context';

export interface SwitchFieldProps {
  label?: React.ReactNode;
  description?: React.ReactNode;
  orientation?: FieldOrientation;
  className?: string;
  disabled?: boolean;
}

export function SwitchField({
  label,
  description,
  orientation = 'horizontal',
  className,
  disabled,
}: SwitchFieldProps) {
  const field = useFieldContext<boolean>();
  return (
    <FormFieldShell
      label={label}
      description={description}
      orientation={orientation}
      className={className}
    >
      {({ id }) => (
        <Switch
          id={id}
          checked={field.state.value ?? false}
          onCheckedChange={(checked) => field.handleChange(checked)}
          onBlur={field.handleBlur}
          disabled={disabled}
        />
      )}
    </FormFieldShell>
  );
}
