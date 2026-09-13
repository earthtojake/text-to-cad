import type { ReactNode } from 'react';
import { useRef } from 'react';
import * as styles from './show-hide.css';

export interface ShowHideProps {
  /** Whether children are currently displayed. */
  visible: boolean;
  children: ReactNode;
  /** Defer mounting children until the first time they become visible. @default false */
  lazy?: boolean;
}

/**
 * Keeps children mounted while toggling their visibility, preserving React
 * and DOM state (terminals, scroll positions, form inputs). Visible children
 * render through `display: contents`, so the wrapper adds no layout box.
 */
export function ShowHide({ visible, children, lazy = false }: ShowHideProps) {
  const hasBeenVisibleRef = useRef(visible);

  if (visible) {
    hasBeenVisibleRef.current = true;
  }

  if (lazy && !hasBeenVisibleRef.current) {
    return null;
  }

  return (
    <div data-slot="show-hide" data-hidden={visible ? undefined : ''} className={styles.root}>
      {children}
    </div>
  );
}
