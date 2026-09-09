import { observer } from 'mobx-react-lite';
import type { ReactNode } from 'react';
import { getMachinesStore } from '@core/features/machines/contributions/app-stores';
import {
  asAvailableProject,
  getProjectStore,
} from '@core/features/projects/api/browser/stores/project-selectors';
import {
  ProjectAvailabilityFrame,
  type ProjectAvailabilityLayout,
} from '@core/features/projects/browser/components/project-availability-banner';
import { useConfirmDeleteProject } from '@core/features/projects/contributions/browser/use-confirm-delete-project';
import { settingsViewDef } from '@core/features/settings/contributions/views';
import { getUpdateStore } from '@core/features/updates/contributions/app-stores';
import { useOpenModal } from '@core/manifests/browser/modal-api';
import { useNavigate } from '@core/primitives/navigation/browser/navigation-hooks';

export const ProjectAvailabilityBoundary = observer(function ProjectAvailabilityBoundary({
  children,
  projectId,
  layout,
}: {
  children: ReactNode;
  projectId: string;
  layout?: ProjectAvailabilityLayout;
}) {
  const context = asAvailableProject(getProjectStore(projectId));
  const confirmDeleteProject = useConfirmDeleteProject();
  const openRelinkProject = useOpenModal('relinkProjectModal');
  const { navigate } = useNavigate();
  if (!context) return children;

  const project = context.project;
  const machine =
    project.type === 'ssh'
      ? getMachinesStore().connections.find((connection) => connection.id === project.connectionId)
      : undefined;
  const openHostDetails = () =>
    navigate(
      project.type === 'ssh'
        ? settingsViewDef({
            tab: 'connections',
            ...(machine ? { detail: [project.connectionId] } : {}),
          })
        : settingsViewDef({ tab: 'system' })
    );
  return (
    <ProjectAvailabilityFrame
      project={project}
      state={context.host.state}
      machineName={machine?.name}
      layout={layout}
      actionHandlers={{
        connect: () => context.host.recover(),
        retry: () => context.host.recover(),
        configure: openHostDetails,
        diagnostics: openHostDetails,
        'update-client': () => {
          navigate(settingsViewDef({ tab: 'general' }));
          void getUpdateStore().check();
        },
        'relink-project': () => openRelinkProject({ projectId }),
        'remove-project': () =>
          confirmDeleteProject({
            projectId,
            projectLabel: project.name,
          }),
      }}
    >
      {children}
    </ProjectAvailabilityFrame>
  );
});
