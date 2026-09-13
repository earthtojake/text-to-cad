import type { IconName } from '@emdash/ui/react/primitives';
import type { ComponentType, ReactNode } from 'react';

export interface SettingsPageProps {
  openDetail: (detailId: string) => void;
}

export interface SettingsPageDetailProps {
  /** Full detail path down to and including this level. */
  path: string[];
  /** This level's own segment (the last element of `path`). */
  detailId: string;
  /** Appends one segment, navigating into this level's child detail. */
  openDetail: (childId: string) => void;
  /** Pops one level. */
  closeDetail: () => void;
}

export interface SettingsPageDetailContribution {
  component: ComponentType<SettingsPageDetailProps>;
  /**
   * Resolves this level's breadcrumb label from the path segments up to and
   * including its own. Returning null marks the segment invalid; the rendered
   * path truncates to the longest valid prefix.
   */
  breadcrumbLabel: (path: string[]) => string | null;
  /** The next detail level below this one, if any. */
  child?: SettingsPageDetailContribution;
}

export interface SettingsPageContribution<TId extends string = string> {
  id: TId;
  label: string;
  icon?: IconName | ReactNode;
  component: ComponentType<SettingsPageProps>;
  detail?: SettingsPageDetailContribution;
}

export function defineSettingsPageContribution<TId extends string>(
  contribution: SettingsPageContribution<TId>
): SettingsPageContribution<TId> {
  return Object.freeze(contribution);
}
