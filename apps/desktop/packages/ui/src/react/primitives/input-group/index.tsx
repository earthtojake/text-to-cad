'use client';

import { cx } from '@styles/utilities/cx';
import type { RecipeVariants } from '@vanilla-extract/recipes';
import * as React from 'react';
// Relative imports: the dts emitter rewrites aliased imports to a dangling
// relative path, silently degrading the prop types.
import { Button } from '../button';
import { Input, type InputProps } from '../input';
import { Textarea } from '../textarea';
import * as styles from './input-group.css';

type InputGroupVariant = NonNullable<RecipeVariants<typeof styles.inputGroup>>['variant'];
export type InputGroupAddonAlign = NonNullable<
  RecipeVariants<typeof styles.inputGroupAddon>
>['align'];

function InputGroupRoot({
  className,
  variant = 'default',
  ...props
}: React.ComponentProps<'div'> & { variant?: InputGroupVariant }) {
  return (
    <div
      data-slot="input-group"
      role="group"
      className={cx(styles.inputGroup({ variant }), className)}
      {...props}
    />
  );
}

function InputGroupAddon({
  className,
  align = 'inline-start',
  ...props
}: React.ComponentProps<'div'> & { align?: InputGroupAddonAlign }) {
  return (
    <div
      role="group"
      data-slot="input-group-addon"
      data-align={align}
      className={cx(styles.inputGroupAddon({ align }), className)}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest('button')) {
          return;
        }
        e.currentTarget.parentElement?.querySelector('input')?.focus();
      }}
      {...props}
    />
  );
}

function InputGroupButton({
  className,
  type = 'button',
  ...props
}: React.ComponentProps<typeof Button> & {
  type?: 'button' | 'submit' | 'reset';
}) {
  return (
    <Button
      type={type}
      size="xs"
      icon
      className={cx(styles.inputGroupButton, className)}
      {...props}
    />
  );
}

function InputGroupText({ className, ...props }: React.ComponentProps<'span'>) {
  return <span className={cx(styles.inputGroupText, className)} {...props} />;
}

function InputGroupInput({ className, size: _size, ...props }: Omit<InputProps, 'bare'>) {
  return (
    <Input
      bare
      data-slot="input-group-control"
      className={cx(styles.inputGroupControl, className)}
      {...props}
    />
  );
}

function InputGroupTextarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return (
    <Textarea
      data-slot="input-group-control"
      className={cx(styles.inputGroupTextareaControl, className)}
      {...props}
    />
  );
}

export const InputGroup = {
  Root: InputGroupRoot,
  Addon: InputGroupAddon,
  Button: InputGroupButton,
  Text: InputGroupText,
  Input: InputGroupInput,
  Textarea: InputGroupTextarea,
};
