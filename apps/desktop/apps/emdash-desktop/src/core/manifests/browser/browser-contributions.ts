import { conversationsBrowserContributions } from '@core/features/conversations/contributions/browser';
import { editorBrowserContributions } from '@core/features/editor/contributions/browser';
import { libraryBrowserContributions } from '@core/features/library/contributions/browser';
import { machinesBrowserContributions } from '@core/features/machines/contributions/browser';
import { projectsBrowserContributions } from '@core/features/projects/contributions/browser';
import { settingsBrowserContributions } from '@core/features/settings/contributions/browser';
import { skillsBrowserContributions } from '@core/features/skills/contributions/browser';
import { sourceControlBrowserContributions } from '@core/features/source-control/contributions/browser';
import { tasksBrowserContributions } from '@core/features/tasks/contributions/browser';
import { workbenchBrowserContributions } from '@core/features/workbench/contributions/browser';

export const featureViewRuntimes = [
  ...workbenchBrowserContributions.views,
  ...projectsBrowserContributions.views,
  ...settingsBrowserContributions.views,
  ...tasksBrowserContributions.views,
] as const;

export const featureModalDefs = [
  ...conversationsBrowserContributions.modalDefs,
  ...editorBrowserContributions.modalDefs,
  ...libraryBrowserContributions.modalDefs,
  ...machinesBrowserContributions.modalDefs,
  ...projectsBrowserContributions.modalDefs,
  ...settingsBrowserContributions.modalDefs,
  ...skillsBrowserContributions.modalDefs,
  ...sourceControlBrowserContributions.modalDefs,
  ...tasksBrowserContributions.modalDefs,
  ...workbenchBrowserContributions.modalDefs,
] as const;
