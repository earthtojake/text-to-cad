import { RadioGroup } from '@react/primitives/radio-group';
import * as React from 'react';
import { FormFieldShell, type FieldOrientation } from '../field-shell';
import { useFieldContext } from '../form-context';
import type { SelectOption } from './select-field';
import * as styles from './radio-group-field.css';

export interface RadioGroupFieldProps {
  options: SelectOption[];
  label?: React.ReactNode;
  description?: React.ReactNode;
  orientation?: FieldOrientation;
  layout?: 'row' | 'stack';
  className?: string;
  disabled?: boolean;
}

export function RadioGroupField({
  options,
  label,
  description,
  orientation,
  layout = 'stack',
  className,
  disabled = false,
}: RadioGroupFieldProps) {
  const field = useFieldContext<string>();

  return (
    <FormFieldShell
      label={label}
      description={description}
      orientation={orientation}
      className={className}
    >
      {({ id, invalid }) => (
        <RadioGroup.Root
          className={styles.radioOptions({ layout })}
          value={field.state.value}
          onValueChange={(value) => {
            if (value !== null) field.handleChange(String(value));
          }}
          onBlur={field.handleBlur}
          aria-labelledby={label != null ? `${id}-label` : undefined}
          aria-invalid={invalid || undefined}
        >
          {options.map((option, index) => {
            const itemId = `${id}-${index}`;
            const itemLabelId = `${itemId}-label`;

            return (
              <label
                key={option.value}
                className={styles.radioOption({ disabled })}
                data-disabled={disabled || undefined}
              >
                <RadioGroup.Item
                  id={itemId}
                  value={option.value}
                  disabled={disabled}
                  aria-labelledby={itemLabelId}
                  aria-invalid={invalid || undefined}
                />
                <span id={itemLabelId}>{option.label}</span>
              </label>
            );
          })}
        </RadioGroup.Root>
      )}
    </FormFieldShell>
  );
}
