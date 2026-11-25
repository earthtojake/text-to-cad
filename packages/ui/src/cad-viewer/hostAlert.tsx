import type { ReactNode } from 'react';
import { english } from '../i18n/index.js';
import type { FileNavigationAction, HostAlert } from '../file-viewer/types.js';
import ViewerAlertCard, { alertNavigationAction } from '../renderers/kit/status/ViewerAlertCard.jsx';

/**
 * A host's own alert (`HostAlert`, `CadViewer`'s `alert`: a failed update of cad) as the file viewer draws it
 * (`FileViewer`'s `alert`): the viewer's alert card, the one every error is said in, which its X or Escape puts away
 * (`onDismiss`) and whose Retry is `onRetry`; put away, no card, and the navbar's icon (`alertNavigationAction`) that
 * brings it back (`onReopen`). None without one.
 */
export function hostAlertSlot(alert: HostAlert | null | undefined, t: (key: string, params?: Record<string, unknown>) => string = english):
  { card: ReactNode; action: FileNavigationAction | null } | null {
  if (!alert) return null;
  return {
    card: alert.dismissed ? null : <ViewerAlertCard alert={alert.alert} hasContent onDismiss={alert.onDismiss}
      onReload={alert.onRetry ?? null} closeOnEscape />,
    action: alert.dismissed ? alertNavigationAction(alert.alert, alert.onReopen, t, 'host-alert') : null,
  };
}
