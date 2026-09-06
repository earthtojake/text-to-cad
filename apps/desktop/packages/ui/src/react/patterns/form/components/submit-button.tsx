import { useStore } from '@tanstack/react-store';
import * as React from 'react';
import { Button, type ButtonProps } from '../../../primitives/button';
import { useFormContext } from '../form-context';

export interface SubmitButtonProps extends Omit<ButtonProps, 'type' | 'disabled'> {
  /** Override the disabled state — in addition to the automatic form-validity check. */
  disabled?: boolean;
}

/**
 * SubmitButton — a `Button` that is automatically disabled while the form is
 * submitting or when it cannot be submitted (e.g. has validation errors on
 * touched fields). Always renders with `type="submit"`.
 */
export function SubmitButton({ children, disabled, ...props }: SubmitButtonProps) {
  const form = useFormContext();
  const isDisabled = useStore(form.store, (s) => s.isSubmitting || !s.canSubmit);
  return (
    <Button type="submit" variant="primary" disabled={isDisabled || disabled} {...props}>
      {children}
    </Button>
  );
}
