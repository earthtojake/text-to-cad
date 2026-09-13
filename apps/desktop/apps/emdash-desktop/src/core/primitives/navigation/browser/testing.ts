import { z } from 'zod';
import { workbenchLayout } from '@core/primitives/layouts/api';
import { defineSubject } from '@core/primitives/subjects/api';
import { defineView, defineViewCatalog } from '@core/primitives/views/api';
import { NavigationHistoryStore } from './navigation-history-store';
import { resetNavigationHost, seedNavigationHost, type NavigationHost } from './navigation-host';
import { NavigationStore } from './navigation-store';

/**
 * Test doubles mirroring the production view surface (home/project/task/
 * settings) closely enough to exercise history keys, subjects, redirects, and
 * location contracts without importing feature contributions.
 */
export const testProjectSubject = defineSubject({
  kind: 'project',
  key: z.object({ projectId: z.string().min(1) }),
  encode: ({ projectId }) => projectId,
});

export const testTaskSubject = defineSubject({
  kind: 'task',
  key: z.object({ taskId: z.string().min(1) }),
  encode: ({ taskId }) => taskId,
});

export const testHomeViewDef = defineView({
  id: 'home',
  params: z.object({}),
  layout: workbenchLayout,
});

export const testProjectViewDef = defineView({
  id: 'project',
  params: z.object({ projectId: z.string().min(1) }),
  layout: workbenchLayout,
  subject: ({ projectId }) => testProjectSubject({ projectId }),
});

export const testTaskViewDef = defineView({
  id: 'task',
  params: z.object({ projectId: z.string().min(1), taskId: z.string().min(1) }),
  layout: workbenchLayout,
  historyKey: ({ taskId }) => taskId,
  subject: ({ taskId }) => testTaskSubject({ taskId }),
  location: {
    schema: z.object({ tabId: z.string() }),
    key: ({ tabId }) => tabId,
  },
});

export const testSettingsViewDef = defineView({
  id: 'settings',
  params: z.object({ tab: z.string().optional() }),
  layout: workbenchLayout,
});

export const testViewCatalog = defineViewCatalog([
  testHomeViewDef,
  testProjectViewDef,
  testTaskViewDef,
  testSettingsViewDef,
] as const);

/**
 * Test-level host setup, mirroring `seedSliceWire`: reset the seam, seed it
 * with the fake view catalog (or overrides), and hand back a disposer. The
 * navigation stores then run unmodified — no renderer host, no feature slices.
 */
export function seedTestNavigationHost(overrides: Partial<NavigationHost> = {}): {
  dispose: () => void;
} {
  resetNavigationHost();
  seedNavigationHost({
    views: testViewCatalog,
    homeRef: () => testHomeViewDef(),
    settingsViewId: testSettingsViewDef.id,
    settingsRef: () => testSettingsViewDef(),
    onError: () => {},
    ...overrides,
  });
  return { dispose: () => resetNavigationHost() };
}

/** Builds real navigation stores against the seeded host, outside the app scope. */
export function createTestNavigation(): {
  navigation: NavigationStore;
  history: NavigationHistoryStore;
} {
  const history = new NavigationHistoryStore();
  return { history, navigation: new NavigationStore(history) };
}
