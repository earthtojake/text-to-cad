import { observer } from 'mobx-react-lite';
import {
  asAvailableProject,
  getProjectStore,
} from '@core/features/projects/api/browser/stores/project-selectors';
import { WorkspaceDetailPage } from '@core/features/workspaces/contributions/browser/workspace-detail-page';
import type { SettingsPageDetailProps } from '@core/primitives/settings/api/page-contribution';

/** Local Workspaces tab detail: path is `[projectId]`. */
export const LocalWorkspaceDetailPage = observer(function LocalWorkspaceDetailPage(
  props: SettingsPageDetailProps
) {
  const project = asAvailableProject(getProjectStore(props.detailId));
  return (
    <WorkspaceDetailPage
      scope={{ kind: 'local' }}
      host={project?.host}
      projectId={props.detailId}
      onDeletedAll={props.closeDetail}
    />
  );
});
