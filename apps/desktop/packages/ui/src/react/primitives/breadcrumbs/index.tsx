import { cx } from '@styles/utilities/cx';
import { ChevronRightIcon } from 'lucide-react';
import type { HTMLAttributes } from 'react';
import * as styles from './breadcrumbs.css';

export interface BreadcrumbItem {
  id: string;
  label: string;
  onSelect?: () => void;
}

export interface BreadcrumbsProps extends HTMLAttributes<HTMLElement> {
  items: readonly BreadcrumbItem[];
  label?: string;
}

export function Breadcrumbs({
  items,
  label = 'Breadcrumb',
  className,
  ...props
}: BreadcrumbsProps) {
  if (items.length === 0) return null;

  return (
    <nav
      aria-label={label}
      data-slot="breadcrumbs"
      className={cx(styles.root, className)}
      {...props}
    >
      <ol className={styles.list}>
        {items.map((item, index) => {
          const current = index === items.length - 1;

          return (
            <li key={item.id} className={styles.item}>
              {index > 0 && (
                <ChevronRightIcon aria-hidden className={styles.separator} strokeWidth={1.5} />
              )}
              {current || !item.onSelect ? (
                <span
                  className={current ? styles.current : styles.label}
                  aria-current={current ? 'page' : undefined}
                >
                  {item.label}
                </span>
              ) : (
                <button type="button" className={styles.link} onClick={item.onSelect}>
                  {item.label}
                </button>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
