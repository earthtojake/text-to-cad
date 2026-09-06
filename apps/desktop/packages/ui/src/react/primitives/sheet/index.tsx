import { Drawer } from '@base-ui/react/drawer';
import { Button } from '@react/primitives/button';
import { ScrollContainer } from '@react/primitives/scroll-container';
import { cx } from '@styles/utilities/cx';
import { XIcon } from 'lucide-react';
import * as React from 'react';
import * as styles from './sheet.css';

export type SheetSide = 'right' | 'left' | 'top' | 'bottom';

// ── Root parts ────────────────────────────────────────────────────────────────

function SheetRoot({ ...props }: Drawer.Root.Props) {
  return <Drawer.Root data-slot="sheet" {...props} />;
}

function SheetTrigger({ ...props }: Drawer.Trigger.Props) {
  return <Drawer.Trigger data-slot="sheet-trigger" {...props} />;
}

function SheetPortal({ ...props }: Drawer.Portal.Props) {
  return <Drawer.Portal data-slot="sheet-portal" {...props} />;
}

function SheetClose({ ...props }: Drawer.Close.Props) {
  return <Drawer.Close data-slot="sheet-close" {...props} />;
}

function SheetBackdrop({ className, ...props }: Drawer.Backdrop.Props) {
  return (
    <Drawer.Backdrop
      data-slot="sheet-backdrop"
      className={cx(styles.backdrop, className)}
      {...props}
    />
  );
}

// ── Content shell ─────────────────────────────────────────────────────────────

function SheetContent({
  className,
  children,
  side = 'right',
  ...props
}: Drawer.Popup.Props & { side?: SheetSide }) {
  return (
    <SheetPortal>
      <SheetBackdrop />
      <Drawer.Popup
        data-slot="sheet-content"
        className={cx('surface-base', styles.sheetContent({ side }), className)}
        {...props}
      >
        {children}
      </Drawer.Popup>
    </SheetPortal>
  );
}

// ── Header / Body / Footer ────────────────────────────────────────────────────

function SheetHeader({
  className,
  children,
  showCloseButton = true,
  ...props
}: React.ComponentProps<'div'> & { showCloseButton?: boolean }) {
  return (
    <div data-slot="sheet-header" className={cx(styles.sheetHeader, className)} {...props}>
      <div className={styles.sheetHeaderInner}>{children}</div>
      {showCloseButton && (
        <Drawer.Close
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
        </Drawer.Close>
      )}
    </div>
  );
}

function SheetTitle({ className, ...props }: Drawer.Title.Props) {
  return (
    <Drawer.Title data-slot="sheet-title" className={cx(styles.sheetTitle, className)} {...props} />
  );
}

function SheetBody({
  className,
  children,
  style,
  maxHeight,
  topFade = true,
}: {
  className?: string;
  children?: React.ReactNode;
  style?: React.CSSProperties;
  maxHeight?: number | string;
  topFade?: boolean;
}) {
  return (
    <ScrollContainer
      maxHeight={maxHeight}
      topFade={topFade}
      style={{ minHeight: 0, flex: '1 1 0%', ...style }}
      viewportClassName={cx(styles.sheetBody, className)}
    >
      {children}
    </ScrollContainer>
  );
}

function SheetFooter({ className, children, ...props }: React.ComponentProps<'div'>) {
  return (
    <div data-slot="sheet-footer" className={cx(styles.sheetFooter, className)} {...props}>
      {children}
    </div>
  );
}

// ── Exports ───────────────────────────────────────────────────────────────────

export const Sheet = {
  Root: SheetRoot,
  Trigger: SheetTrigger,
  Portal: SheetPortal,
  Close: SheetClose,
  Content: SheetContent,
  Header: SheetHeader,
  Title: SheetTitle,
  Body: SheetBody,
  Footer: SheetFooter,
};
