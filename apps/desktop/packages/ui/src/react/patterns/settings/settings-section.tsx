import { SeparatedList } from '@react/primitives/separated-list';
import { Heading } from '@react/primitives/typography/Heading';
import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import { SettingsCard } from './settings-card';
import * as styles from './settings.css';

export interface SettingsSectionProps {
  /** Optional section heading rendered above the card, inset to align with card content. */
  title?: React.ReactNode;
  /**
   * Gap between rows inside the card's `SeparatedList`.
   * Default: `'1rem'`, matching existing settings pages.
   */
  gap?: string;
  /**
   * When true the section renders children as-is under the heading — for
   * content that brings its own surface (a custom card, a tile grid).
   * Default: false, wrapping children in `SettingsCard` + `SeparatedList`.
   */
  bare?: boolean;
  children: React.ReactNode;
  className?: string;
}

/**
 * SettingsSection — the canonical settings-page section: an optional level-3
 * heading above a `SettingsCard` whose children are separated rows.
 *
 * Usage:
 * ```tsx
 * <SettingsSection title="Preferences">
 *   <SettingsRow label="Automatic updates" control={<Switch />} />
 *   <SettingsRow label="Telemetry" control={<Switch />} />
 * </SettingsSection>
 * ```
 *
 * Sections stack on the page with page-owned spacing; the section only owns
 * the heading-to-card gap and the card shell.
 */
export function SettingsSection({
  title,
  gap = '1rem',
  bare = false,
  children,
  className,
}: SettingsSectionProps) {
  return (
    <section data-slot="settings-section" className={cx(styles.section, className)}>
      {title != null && (
        <Heading level={3} className={styles.sectionTitle}>
          {title}
        </Heading>
      )}
      {bare ? (
        children
      ) : (
        <SettingsCard>
          <SeparatedList gap={gap} direction="column">
            {children}
          </SeparatedList>
        </SettingsCard>
      )}
    </section>
  );
}
