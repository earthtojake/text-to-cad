import { ComboboxPopover } from '@/react/components/combobox-popover';
import { FormFieldShell, type FieldOrientation } from '../field-shell';
import { useFieldContext } from '../form-context';
import type { SelectOption } from './select-field';

export interface ComboboxSelectFieldProps {
  options: SelectOption[];
  label?: React.ReactNode;
  description?: React.ReactNode;
  orientation?: FieldOrientation;
  searchPlaceholder?: string;
  placeholder?: string;
  disabled?: boolean;
}

export function ComboboxSelectField({
  options,
  label,
  description,
  orientation,
  searchPlaceholder,
  placeholder,
  disabled,
}: ComboboxSelectFieldProps) {
  const field = useFieldContext<string>();
  return (
    <FormFieldShell label={label} description={description} orientation={orientation}>
      {() => (
        <ComboboxPopover
          appearance="input"
          items={options}
          value={field.state.value}
          onValueChange={field.handleChange}
          itemToKey={(o) => o.value}
          itemToLabel={(o) => String(o.label)}
          renderTrigger={(sel) => sel?.label ?? placeholder ?? 'Select…'}
          renderItem={(o) => o.label}
          searchPlaceholder={searchPlaceholder}
          disabled={disabled}
        />
      )}
    </FormFieldShell>
  );
}
