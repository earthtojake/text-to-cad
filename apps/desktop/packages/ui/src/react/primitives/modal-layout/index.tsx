import type { ReactNode } from 'react';
import { AnimatedHeight } from '../animated-height';

export interface ModalLayoutProps {
  header: ReactNode;
  footer: ReactNode;
  children: ReactNode;
}

/**
 * Standard modal composition: a static header and footer around a middle
 * section that height-animates as its content changes (e.g. between steps
 * or validation states).
 */
export function ModalLayout({ header, footer, children }: ModalLayoutProps) {
  return (
    <>
      {header}
      <AnimatedHeight>{children}</AnimatedHeight>
      {footer}
    </>
  );
}
