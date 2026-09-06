import { Select } from '@react/primitives/select';
import * as React from 'react';
import { FormFieldShell, type FieldOrientation } from '../field-shell';
import { useFieldContext } from '../form-context';

export interface SelectOption {
  value: string;
  label: React.ReactNode;
}

export interface SelectFieldProps {
  options: SelectOption[];
  label?: React.ReactNode;
  description?: React.ReactNode;
  orientation?: FieldOrientation;
  className?: string;
  placeholder?: string;
  disabled?: boolean;
}

export function SelectField({
  options,
  label,
  description,
  orientation,
  className,
  placeholder,
  disabled,
}: SelectFieldProps) {
  const field = useFieldContext<string>();
  return (
    <FormFieldShell
      label={label}
      description={description}
      orientation={orientation}
      className={className}
    >
      {({ id }) => (
        <Select.Root
          value={field.state.value}
          onValueChange={(value) => {
            if (value !== null) field.handleChange(value);
          }}
          disabled={disabled}
        >
          <Select.Trigger id={id} onBlur={field.handleBlur} appearance="input">
            <Select.Value placeholder={placeholder} />
          </Select.Trigger>
          <Select.Content>
            {options.map((opt) => (
              <Select.Item key={opt.value} value={opt.value}>
                {opt.label}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      )}
    </FormFieldShell>
  );
}
