import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './settings.css';
import { card as cardRecipe } from '@styles/recipes/card.css';

export interface SettingsCardProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * SettingsCard — a neutral, rounded surface for grouping related settings.
 *
 * Uses the base surface level so it reads grayish in light mode and slightly
 * elevated in dark mode. Callers add their own header markup when needed.
 */
export function SettingsCard({ children, className }: SettingsCardProps) {
  return (
    <div
      data-slot="settings-card"
      className={cx(
        cardRecipe({ level: 'base', padding: 'lg', radius: 'lg' }),
        styles.card,
        className
      )}
    >
      <div data-slot="settings-card-body" className={styles.body}>
        {children}
      </div>
    </div>
  );
}
