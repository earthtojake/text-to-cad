import { addProjectModal } from '../browser/components/add-project-modal/add-project-modal';
import { directorySelectorModal } from '../browser/components/directory-selector-modal';
import { relinkProjectModal } from '../browser/components/relink-project-modal';
import { projectConfigImportModal } from '../browser/components/settings-view/project-config-import-modal';
import { shareProjectConfigModal } from '../browser/components/settings-view/share-project-config-modal';
import { useOpenProjectFolder } from '../browser/open-project-folder';
import { projectViewRuntime } from '../browser/view';
import { projectAvailabilityUiContribution } from './browser/project-availability-ui';

export const projectsBrowserContributions = {
  views: [projectViewRuntime],
  modalDefs: [
    addProjectModal,
    shareProjectConfigModal,
    projectConfigImportModal,
    directorySelectorModal,
    relinkProjectModal,
  ],
  projectAvailabilityUi: projectAvailabilityUiContribution,
  useOpenProjectFolder,
} as const;
