import { settingsViewDef } from '@core/features/settings/contributions/views';
import { homeViewDef } from '@core/features/workbench/contributions/views';
import { viewCatalog } from '@core/manifests/browser/view-catalog';
import { log } from '@core/primitives/logging/browser/logger';
import {
  resetNavigationHost,
  seedNavigationHost,
} from '@core/primitives/navigation/browser/navigation-host';

/**
 * The production seed: called once by the renderer bootstrap before the app
 * scope builds the navigation stores. This is the only host-owned navigation
 * code — it hands the aggregated view catalog and the well-known home/settings
 * refs to the core seam so the primitive never imports feature manifests.
 */
export function seedRendererNavigationHost(): void {
  seedNavigationHost({
    views: viewCatalog,
    homeRef: () => homeViewDef(),
    settingsViewId: settingsViewDef.id,
    settingsRef: () => settingsViewDef(),
    onError: (message, error) => log.error(message, error),
  });
}

// Dev-server edits to seeding modules must not leave a stale host behind.
import.meta.hot?.dispose(() => resetNavigationHost());
