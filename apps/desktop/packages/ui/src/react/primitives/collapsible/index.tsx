'use client';

import { Collapsible as CollapsiblePrimitive } from '@base-ui/react/collapsible';
import { cx } from '@styles/utilities/cx';
import { ChevronDownIcon } from 'lucide-react';
import * as React from 'react';
import * as styles from './collapsible.css';

// ── Root ──────────────────────────────────────────────────────────────────────

function CollapsibleRoot({ ...props }: CollapsiblePrimitive.Root.Props) {
  return <CollapsiblePrimitive.Root data-slot="collapsible" {...props} />;
}

// ── Trigger ───────────────────────────────────────────────────────────────────

export interface CollapsibleTriggerProps extends CollapsiblePrimitive.Trigger.Props {
  /** Hide the trailing chevron icon. @default false */
  hideChevron?: boolean;
}

function CollapsibleTrigger({
  className,
  hideChevron = false,
  children,
  ...props
}: CollapsibleTriggerProps) {
  return (
    <CollapsiblePrimitive.Trigger
      data-slot="collapsible-trigger"
      className={cx(styles.trigger, className)}
      {...props}
    >
      {children}
      {!hideChevron && <ChevronDownIcon className={styles.chevron} aria-hidden />}
    </CollapsiblePrimitive.Trigger>
  );
}

// ── Panel ─────────────────────────────────────────────────────────────────────

function CollapsiblePanel({ className, ...props }: CollapsiblePrimitive.Panel.Props) {
  return (
    <CollapsiblePrimitive.Panel
      data-slot="collapsible-panel"
      className={cx(styles.panel, className)}
      {...props}
    />
  );
}

export const Collapsible = {
  Root: CollapsibleRoot,
  Trigger: CollapsibleTrigger,
  Panel: CollapsiblePanel,
};
