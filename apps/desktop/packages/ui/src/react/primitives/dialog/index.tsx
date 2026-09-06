import { Dialog as DialogPrimitive } from '@base-ui/react/dialog';
import { Button } from '@react/primitives/button';
import { cx } from '@styles/utilities/cx';
import { XIcon } from 'lucide-react';
import * as React from 'react';
import * as styles from './dialog.css';

export type DialogSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'full';

// ── Root parts ────────────────────────────────────────────────────────────────

function DialogRoot({ ...props }: DialogPrimitive.Root.Props) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />;
}

function DialogTrigger({ ...props }: DialogPrimitive.Trigger.Props) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />;
}

function DialogPortal({ ...props }: DialogPrimitive.Portal.Props) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />;
}

function DialogClose({ ...props }: DialogPrimitive.Close.Props) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />;
}

function DialogOverlay({ className, ...props }: DialogPrimitive.Backdrop.Props) {
  return (
    <DialogPrimitive.Backdrop
      data-slot="dialog-overlay"
      className={cx(styles.overlay, className)}
      {...props}
    />
  );
}

// ── Content shell ─────────────────────────────────────────────────────────────

function DialogContent({
  className,
  children,
  size = 'md',
  onKeyDownCapture,
  ...props
}: DialogPrimitive.Popup.Props & { size?: DialogSize }) {
  return (
    <DialogPortal>
      <DialogOverlay />
      <div className={styles.positioner}>
        <DialogPrimitive.Popup
          data-slot="dialog-content"
          className={cx('surface-elevated', styles.content({ size }), className)}
          onKeyDownCapture={(event) => {
            // The global `app.confirm` keybinding (modifier+Enter) already drives
            // confirm buttons inside dialogs; swallow the browser default so the
            // focused control doesn't handle the same press a second time.
            if ((event.metaKey || event.ctrlKey || event.altKey) && event.key === 'Enter') {
              event.preventDefault();
            }
            onKeyDownCapture?.(event);
          }}
          {...props}
        >
          {children}
        </DialogPrimitive.Popup>
      </div>
    </DialogPortal>
  );
}

// ── Header / Body / Footer ────────────────────────────────────────────────────

function DialogHeader({
  className,
  children,
  showCloseButton = true,
  ...props
}: React.ComponentProps<'div'> & { showCloseButton?: boolean }) {
  return (
    <div data-slot="dialog-header" className={cx(styles.header, className)} {...props}>
      <div className={styles.headerInner}>{children}</div>
      {showCloseButton && (
        <DialogPrimitive.Close
          render={
            <Button
              variant="ghost"
              size="xs"
              icon
              aria-label="Close"
              className={styles.closeButtonOverride}
            />
          }
        >
          <XIcon style={{ width: '1rem', height: '1rem' }} />
        </DialogPrimitive.Close>
      )}
    </div>
  );
}

function toCssSize(size: number | string | undefined): string | undefined {
  return typeof size === 'number' ? `${size}px` : size;
}

function DialogBody({
  className,
  children,
  style,
  height,
  maxHeight,
  topFade = true,
}: {
  className?: string;
  children?: React.ReactNode;
  style?: React.CSSProperties;
  /** Fixed body height; when omitted the body fills the dialog content. */
  height?: number | string;
  maxHeight?: number | string;
  topFade?: boolean;
}) {
  return (
    <div
      data-slot="dialog-body"
      className={cx(
        'scroll-fade',
        'scroll-fade__viewport',
        !topFade && 'sf-no-top',
        styles.body,
        className
      )}
      style={{
        height: toCssSize(height) ?? '100%',
        minHeight: 0,
        maxHeight: toCssSize(maxHeight),
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function DialogFooter({
  className,
  children,
  showCloseButton = false,
  ...props
}: React.ComponentProps<'div'> & { showCloseButton?: boolean }) {
  return (
    <div data-slot="dialog-footer" className={cx(styles.footer, className)} {...props}>
      {children}
      {showCloseButton && (
        <DialogPrimitive.Close render={<Button variant="secondary" />}>Close</DialogPrimitive.Close>
      )}
    </div>
  );
}

function DialogTitle({ className, ...props }: DialogPrimitive.Title.Props) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cx(styles.title, className)}
      {...props}
    />
  );
}

function DialogDescription({ className, ...props }: DialogPrimitive.Description.Props) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cx(styles.description, className)}
      {...props}
    />
  );
}

export const Dialog = {
  Root: DialogRoot,
  Trigger: DialogTrigger,
  Portal: DialogPortal,
  Close: DialogClose,
  Overlay: DialogOverlay,
  Content: DialogContent,
  Header: DialogHeader,
  Body: DialogBody,
  Footer: DialogFooter,
  Title: DialogTitle,
  Description: DialogDescription,
};
