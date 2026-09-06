import { getProjectManagerStore } from '@core/features/projects/api/browser/stores/project-selectors';
import { ProjectViewWrapper } from '@core/features/projects/contributions/browser/project-view-wrapper';
import { projectViewDef } from '@core/features/projects/contributions/views';
import { homeViewDef } from '@core/features/workbench/contributions/views';
import { defineViewRuntime } from '@core/primitives/views/react';
import { ProjectMainPanel } from './components/main-panel/main-panel';

function ProjectMainPanelSlot() {
  return <ProjectMainPanel />;
}

export const projectViewRuntime = defineViewRuntime(projectViewDef, {
  slots: {
    wrap: ProjectViewWrapper,
    main: ProjectMainPanelSlot,
  },
  resolve: ({ projectId }) => {
    return getProjectManagerStore().projects.has(projectId) ||
      getProjectManagerStore().pendingCreationIds.has(projectId)
      ? { kind: 'ok' }
      : { kind: 'redirect', ref: homeViewDef() };
  },
});
