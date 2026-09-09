import { Tabs as TabsPrimitive } from '@base-ui/react/tabs';
import { controlVariants } from '@styles/recipes/control';
import { cx } from '@styles/utilities/cx';
import * as React from 'react';
// Relative type import: the dts emitter rewrites `@styles/*` type imports to a
// dangling relative path, silently degrading the variant prop types.
import type { ControlVariantProps } from '../../../styles/recipes/control';
import * as styles from './tabs.css';

// ── Root ──────────────────────────────────────────────────────────────────────

const TabsRoot = TabsPrimitive.Root;

// ── List ──────────────────────────────────────────────────────────────────────

function TabsList({ className, ...props }: TabsPrimitive.List.Props) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cx(styles.tabsList, className)}
      {...props}
    />
  );
}

// ── Tab ───────────────────────────────────────────────────────────────────────

export interface TabsTabProps extends TabsPrimitive.Tab.Props {
  size?: ControlVariantProps['size'];
  tone?: ControlVariantProps['tone'];
}

const TabsTab = React.forwardRef<HTMLButtonElement, TabsTabProps>(function TabsTab(
  { className, size = 'xs', tone = 'neutral', ...props },
  ref
) {
  return (
    <TabsPrimitive.Tab
      ref={ref}
      data-slot="tabs-tab"
      className={cx(controlVariants({ variant: 'ghost', tone, size }), styles.tab, className)}
      {...props}
    />
  );
});

// ── Panel ─────────────────────────────────────────────────────────────────────

function TabsPanel({ className, ...props }: TabsPrimitive.Panel.Props) {
  return (
    <TabsPrimitive.Panel
      data-slot="tabs-panel"
      className={cx(styles.tabsPanel, className)}
      {...props}
    />
  );
}

export const Tabs = {
  Root: TabsRoot,
  List: TabsList,
  Tab: TabsTab,
  Panel: TabsPanel,
};
