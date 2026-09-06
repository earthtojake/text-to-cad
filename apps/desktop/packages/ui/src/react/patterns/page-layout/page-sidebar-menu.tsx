import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import { Icon, type IconName } from '../../primitives/icon';
import * as styles from './page-sidebar-menu.css';

type CSSExtra = { [key: string]: string };

// ── Types ─────────────────────────────────────────────────────────────────────

export interface PageNavItem {
  /** Distinguishes this item from a divider; may be omitted. */
  kind?: undefined;
  id: string;
  label: string;
  /** Optional kebab-case Lucide icon name or a custom icon element. */
  icon?: IconName | React.ReactNode;
  /** When true an external-link icon is shown and the active state is suppressed. */
  isExternal?: boolean;
  /** Optional compact value displayed at the trailing edge. */
  badge?: string;
}

export interface PageNavDivider {
  kind: 'divider';
  /**
   * @deprecated Use PageNavSection instead. Labeled dividers still render as
   * section labels for compatibility.
   */
  label?: string;
}

export interface PageNavSection {
  kind: 'section';
  id: string;
  label: string;
}

export type PageSidebarMenuItem = PageNavItem | PageNavDivider | PageNavSection;

export interface PageSidebarMenuProps {
  items: PageSidebarMenuItem[];
  activeId: string;
  onSelect: (item: PageNavItem) => void;
  /**
   * Adds an Electron window drag region to the sticky wrapper.
   * The nav buttons themselves are always excluded from the drag region.
   * Default: false.
   */
  draggable?: boolean;
  className?: string;
  header?: React.ReactNode;
  footer?: React.ReactNode;
  emptyMessage?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * PageLayout.SidebarMenu — a self-contained sticky nav with clickable items.
 *
 * Generalizes the `PageSidebarMenu` used in the Library and Settings views:
 * sticky wrapper, w-52 nav column, idle/hover/active button states.
 *
 * Usage:
 * ```tsx
 * <PageLayout sidebar={
 *   <PageLayout.SidebarMenu
 *     items={[{ id: 'prompts', label: 'Prompts' }, { id: 'skills', label: 'Skills' }]}
 *     activeId={tab}
 *     onSelect={(item) => setTab(item.id)}
 *   />
 * }>
 *   …
 * </PageLayout>
 * ```
 */
function PageSidebarMenu({
  items,
  activeId,
  onSelect,
  draggable = false,
  className,
  header,
  footer,
  emptyMessage,
}: PageSidebarMenuProps) {
  // Inline style type-cast for Electron drag region so vanilla-extract is not
  // involved (no CSS file needed for this runtime-conditional style).
  const wrapperStyle: React.CSSProperties & CSSExtra = draggable ? { WebkitAppRegion: 'drag' } : {};

  return (
    <div className={cx(styles.wrapper, className)} style={wrapperStyle}>
      {header && <div className={styles.header}>{header}</div>}
      <nav className={styles.nav}>
        {items.length === 0 && emptyMessage && (
          <div className={styles.emptyMessage}>{emptyMessage}</div>
        )}
        {items.map((item, index) => {
          if (item.kind === 'divider') {
            return <NavDivider key={`divider-${index}`} label={item.label} />;
          }

          if (item.kind === 'section') {
            return <NavSection key={`section-${item.id}`} label={item.label} />;
          }

          const { id, label, icon, isExternal, badge } = item;
          const isActive = id === activeId && !isExternal;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onSelect(item)}
              className={styles.navItem({ active: isActive })}
            >
              {icon &&
                (typeof icon === 'string' ? (
                  <Icon name={icon as IconName} size="sm" className={styles.navItemIcon} />
                ) : (
                  <span className={styles.navItemIcon}>{icon}</span>
                ))}
              <span className={styles.navItemLabel}>{label}</span>
              {badge && <span className={styles.badge}>{badge}</span>}
              {isExternal && (
                <Icon name="external-link" size="xs" className={styles.externalIcon} />
              )}
            </button>
          );
        })}
      </nav>
      {footer && <div className={styles.footer}>{footer}</div>}
    </div>
  );
}

function NavDivider({ label }: { label?: string }) {
  if (label) {
    return <NavSection label={label} />;
  }

  return <div className={styles.divider} role="separator" />;
}

function NavSection({ label }: { label: string }) {
  return <div className={styles.sectionLabel}>{label}</div>;
}

export { PageSidebarMenu };
