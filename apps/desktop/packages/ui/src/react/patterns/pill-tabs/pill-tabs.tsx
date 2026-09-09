import { Tabs as TabsPrimitive } from '@base-ui/react/tabs';
import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './pill-tabs.css';

export type PillTabsLabelVisibility = 'always' | 'active-only';

export interface PillTab<TValue extends string> {
  value: TValue;
  label: string;
  icon: React.ReactNode;
  disabled?: boolean;
}

export interface PillTabsProps<TValue extends string> {
  items: readonly PillTab<TValue>[];
  value: TValue;
  onValueChange: (value: TValue) => void;
  ariaLabel: string;
  panelId?: string;
  labelVisibility?: PillTabsLabelVisibility;
  className?: string;
}

export function getPillTabId(panelId: string, value: string): string {
  return `${panelId}-tab-${value}`;
}

export function PillTabs<TValue extends string>({
  items,
  value,
  onValueChange,
  ariaLabel,
  panelId,
  labelVisibility = 'always',
  className,
}: PillTabsProps<TValue>) {
  return (
    <TabsPrimitive.Root
      value={value}
      onValueChange={(nextValue) => {
        if (nextValue != null) onValueChange(nextValue as TValue);
      }}
    >
      <TabsPrimitive.List
        data-slot="pill-tabs-list"
        aria-label={ariaLabel}
        activateOnFocus
        className={cx(styles.list, className)}
      >
        {items.map((item) => {
          const active = item.value === value;
          const compact = labelVisibility === 'active-only' && !active;
          return (
            <div
              key={item.value}
              role="presentation"
              data-compact={compact ? 'true' : undefined}
              className={styles.slot({ compact })}
            >
              <TabsPrimitive.Tab
                value={item.value}
                disabled={item.disabled}
                id={panelId ? getPillTabId(panelId, item.value) : undefined}
                aria-controls={panelId}
                render={<button type="button" aria-label={item.label} className={styles.tab} />}
              >
                <span className={styles.content}>
                  <span aria-hidden className={styles.icon}>
                    {item.icon}
                  </span>
                  <span
                    aria-hidden
                    data-hidden={compact ? 'true' : undefined}
                    className={styles.label({ hidden: compact })}
                  >
                    {item.label}
                  </span>
                </span>
              </TabsPrimitive.Tab>
            </div>
          );
        })}
      </TabsPrimitive.List>
    </TabsPrimitive.Root>
  );
}
