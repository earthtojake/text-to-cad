import { Field } from '@react/primitives/field';
import * as React from 'react';

export interface SettingsRowProps {
  label: React.ReactNode;
  description?: React.ReactNode;
  control: React.ReactNode;
  htmlFor?: string;
  controlClassName?: string;
  className?: string;
}

/**
 * SettingsRow — label and supporting text paired with a right-aligned control.
 *
 * Use this for custom or externally controlled settings. Form-backed settings
 * can use the horizontal fields from `@emdash/ui/react/form` directly.
 */
export function SettingsRow({
  label,
  description,
  control,
  htmlFor,
  controlClassName,
  className,
}: SettingsRowProps) {
  return (
    <Field.Root orientation="horizontal" className={className}>
      <Field.Content>
        <Field.Label htmlFor={htmlFor}>{label}</Field.Label>
        {description != null && <Field.Description>{description}</Field.Description>}
      </Field.Content>
      <Field.ControlSlot className={controlClassName}>{control}</Field.ControlSlot>
    </Field.Root>
  );
}
