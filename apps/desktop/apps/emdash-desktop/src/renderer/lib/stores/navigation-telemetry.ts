import type { Unsubscribe } from '@emdash/shared';
import { viewCatalog, type ViewId } from '@core/manifests/browser/view-catalog';
import type { NavigationStore } from '@core/primitives/navigation/browser/navigation-store';
import { captureTelemetry } from '@core/primitives/telemetry/browser/telemetry-client';

type ViewTelemetryEvent = NonNullable<(typeof viewCatalog.defs)[number]['telemetryEvent']>;

export function wireNavigationTelemetry(navigation: NavigationStore): Unsubscribe {
  return navigation.onDidNavigate.subscribe(({ from, to }) => {
    if (from?.viewId === to.viewId) return;
    const event: ViewTelemetryEvent | undefined = viewCatalog.byId(to.viewId)?.telemetryEvent;
    if (event) {
      captureTelemetry(event, {
        from_view: (from?.viewId as ViewId | undefined) ?? null,
      });
    }
  });
}
