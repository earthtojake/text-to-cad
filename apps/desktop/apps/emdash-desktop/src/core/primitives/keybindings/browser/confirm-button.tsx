import { Button, type ButtonProps } from '@emdash/ui/react/primitives';
import { useRef } from 'react';
import { BoundShortcut } from './shortcut';
import { useConfirm } from './use-confirm';

export function ConfirmButton({ disabled, children, ...props }: ButtonProps) {
  const ref = useRef<HTMLButtonElement>(null);
  useConfirm(() => ref.current?.click(), {
    enabled: !disabled,
  });

  return (
    <Button
      ref={ref}
      disabled={disabled}
      kbd={<BoundShortcut command="app.confirm" bare />}
      {...props}
    >
      {children}
    </Button>
  );
}
