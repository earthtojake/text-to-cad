/**
 * ComboboxPopup
 *
 * A reusable floating listbox anchored to a caret position (or any DOMRect).
 * Designed for TipTap suggestion menus but usable wherever a lightweight
 * anchor-positioned popup list is needed.
 *
 * Keyboard navigation is externally driven: the host TipTap extension forwards
 * key events to the imperative `onKeyDown` handle. ArrowUp / ArrowDown move the
 * highlight, Enter / Tab confirm, Escape returns false so the caller can dismiss.
 *
 * Visual language mirrors ComboboxContent / ComboboxItem from combobox.tsx:
 * surface-elevated, ring-1, shadow, rounded-md, text-sm items with bg-surface-hover
 * on highlight and text-foreground-muted descriptions.
 */

import { cx } from '@styles/utilities/cx';
import { XIcon } from 'lucide-react';
import * as React from 'react';
import { createPortal } from 'react-dom';
import * as styles from './combobox-popup.css';

// ── Public types ──────────────────────────────────────────────────────────────

export interface ComboboxPopupItem {
  id: string;
  /** Optional icon node rendered before the label (e.g. a devicon <i> or lucide svg). */
  icon?: React.ReactNode;
  /** Primary display text. */
  label: string;
  /** Secondary muted text shown on the right. */
  description?: string;
  /** Optional visual grouping label rendered as a non-selectable header. */
  section?: string;
}

export interface ComboboxPopupHandle {
  onKeyDown(event: KeyboardEvent): boolean;
}

interface ComboboxPopupProps {
  items: ComboboxPopupItem[];
  /** Caret-position anchor. Popup renders nothing when null or empty. */
  anchorRect: DOMRect | null;
  onSelect(item: ComboboxPopupItem): void;
  /** Text shown when items is empty but anchorRect is set. Omit to hide popup when empty. */
  emptyLabel?: string;
  /** Optional header node rendered above the item list. */
  header?: React.ReactNode;
  /** Render label and description as two stacked rows instead of a single row. */
  stacked?: boolean;
  className?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export const ComboboxPopup = React.forwardRef<ComboboxPopupHandle, ComboboxPopupProps>(
  function ComboboxPopup(
    { items, anchorRect, onSelect, emptyLabel, header, stacked = false, className },
    ref
  ) {
    const [selectedIndex, setSelectedIndex] = React.useState(0);
    const listRef = React.useRef<HTMLUListElement>(null);

    // Reset selection when the item list changes.
    React.useEffect(() => {
      setSelectedIndex(0);
    }, [items]);

    // Scroll the highlighted item into view.
    React.useEffect(() => {
      const el = listRef.current?.querySelector<HTMLElement>(
        `[data-popup-item-index="${selectedIndex}"]`
      );
      el?.scrollIntoView({ block: 'nearest' });
    }, [selectedIndex]);

    React.useImperativeHandle(ref, () => ({
      onKeyDown(event: KeyboardEvent): boolean {
        if (event.key === 'ArrowDown') {
          setSelectedIndex((i) => Math.min(i + 1, items.length - 1));
          return true;
        }
        if (event.key === 'ArrowUp') {
          setSelectedIndex((i) => Math.max(i - 1, 0));
          return true;
        }
        if (event.key === 'Enter' || event.key === 'Tab') {
          const item = items[selectedIndex];
          if (item) onSelect(item);
          return true;
        }
        if (event.key === 'Escape') {
          return false;
        }
        return false;
      },
    }));

    // Nothing to render.
    if (!anchorRect) return null;
    if (items.length === 0 && !emptyLabel) return null;

    // Position above or below the caret depending on available space.
    const spaceBelow = window.innerHeight - anchorRect.bottom;
    const spaceAbove = anchorRect.top;
    const openAbove = spaceBelow < 200 && spaceAbove > spaceBelow;

    const style: React.CSSProperties = openAbove
      ? {
          position: 'fixed',
          left: anchorRect.left,
          bottom: window.innerHeight - anchorRect.top + 4,
        }
      : {
          position: 'fixed',
          left: anchorRect.left,
          top: anchorRect.bottom + 4,
        };

    const popup = (
      <div
        role="listbox"
        style={style}
        className={cx('surface-elevated', styles.popupRoot, className)}
      >
        {header && <div className={styles.popupHeader}>{header}</div>}
        <ul ref={listRef} className={styles.popupList}>
          {items.length === 0 && emptyLabel ? (
            <li className={cx(styles.popupItem, styles.popupItemDefault)}>{emptyLabel}</li>
          ) : (
            items.map((item, index) => {
              const showSection = item.section && item.section !== items[index - 1]?.section;
              return (
                <React.Fragment key={item.id}>
                  {showSection && (
                    <li className={styles.popupSectionHeader} role="presentation">
                      {item.section}
                    </li>
                  )}
                  <li
                    role="option"
                    aria-selected={index === selectedIndex}
                    data-popup-item-index={index}
                    onMouseDown={(e) => {
                      // Prevent editor blur before select fires.
                      e.preventDefault();
                      onSelect(item);
                    }}
                    onMouseEnter={() => setSelectedIndex(index)}
                    className={cx(
                      styles.popupItem,
                      stacked && styles.popupItemStacked,
                      index === selectedIndex ? styles.popupItemHighlighted : styles.popupItemHover
                    )}
                  >
                    {item.icon && <span className={styles.popupItemIcon}>{item.icon}</span>}
                    {stacked ? (
                      <span className={styles.popupItemTextStack}>
                        <span className={styles.popupItemLabel}>{item.label}</span>
                        {item.description && (
                          <span className={styles.popupItemDescription}>{item.description}</span>
                        )}
                      </span>
                    ) : (
                      <>
                        <span className={styles.popupItemLabel}>{item.label}</span>
                        {item.description && (
                          <span className={styles.popupItemDescription}>{item.description}</span>
                        )}
                      </>
                    )}
                  </li>
                </React.Fragment>
              );
            })
          )}
        </ul>
      </div>
    );

    return createPortal(popup, document.body);
  }
);

// ── Helper: dismiss button ────────────────────────────────────────────────────

/** Small icon-only dismiss button used inside ComboboxPopup headers. */
export function ComboboxPopupDismiss({
  onClick,
  className,
}: {
  onClick?: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onMouseDown={(e) => {
        e.preventDefault();
        onClick?.();
      }}
      className={cx(styles.popupDismiss, className)}
      aria-label="Dismiss"
    >
      <XIcon style={{ width: '0.75rem', height: '0.75rem' }} />
    </button>
  );
}
