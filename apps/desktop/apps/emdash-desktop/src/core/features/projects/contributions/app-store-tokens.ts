import type { ProjectManagerStore } from '@core/features/projects/api/browser/stores/project-manager';
import { scopedStoreToken } from '@core/primitives/scoped-stores/browser';

/**
 * App-scope token for the ProjectManagerStore. Kept in a token-only module so
 * other slices' contributions can resolve the store through the scoped-store
 * lookup without a runtime dependency on the store implementation.
 */
export const projectManagerStoreToken = scopedStoreToken<ProjectManagerStore>('projects.manager');
