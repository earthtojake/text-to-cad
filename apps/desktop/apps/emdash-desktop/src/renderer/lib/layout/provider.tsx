import { reaction } from 'mobx';
import { observer } from 'mobx-react-lite';
import { useEffect, type ReactNode } from 'react';
import { viewCatalog } from '@core/manifests/browser/view-catalog';
import { getNavigation } from '@core/primitives/navigation/browser/navigation-selectors';
import type { FocusView } from '@core/primitives/telemetry/api/telemetry';
import { focusTracker } from '@core/primitives/telemetry/browser/focus-tracker';
import { captureTelemetry } from '@core/primitives/telemetry/browser/telemetry-client';
import {
  clearTelemetryTaskScope,
  setTelemetryTaskScope,
} from '@core/primitives/telemetry/browser/telemetry-scope';
import type { ViewRef } from '@core/primitives/views/api';

function syncTelemetryScope(ref: ViewRef): void {
  if (ref.viewId !== 'task') {
    clearTelemetryTaskScope();
    return;
  }

  const taskParams = ref.params as { projectId?: unknown; taskId?: unknown };
  if (
    taskParams &&
    typeof taskParams.projectId === 'string' &&
    typeof taskParams.taskId === 'string'
  ) {
    setTelemetryTaskScope({ projectId: taskParams.projectId, taskId: taskParams.taskId });
    return;
  }

  clearTelemetryTaskScope();
}

export const WorkspaceViewProvider = observer(function WorkspaceViewProvider({
  children,
}: {
  children: ReactNode;
}) {
  useEffect(() => {
    const initialViewId = getNavigation().currentViewId;
    focusTracker.initialize({ view: initialViewId as FocusView });
    syncTelemetryScope(getNavigation().currentRef);
    const event = viewCatalog.byId(initialViewId)?.telemetryEvent;
    if (event) captureTelemetry(event, { from_view: null });
  }, []);

  useEffect(() => {
    return reaction(
      () => getNavigation().currentRef,
      (ref) => syncTelemetryScope(ref)
    );
  }, []);

  return <>{children}</>;
});
