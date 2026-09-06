import { DEFAULT_PROJECT_LIVE_ACTION_DISABLED_REASON } from '../../browser/project-availability-presentation';
import { ProjectAvailabilityBoundary } from './project-availability-boundary';
import {
  getProjectLiveActionDisabledReason,
  ProjectLiveActionGuard,
} from './project-live-action-guard';

export const projectAvailabilityUiContribution = {
  Boundary: ProjectAvailabilityBoundary,
  LiveActionGuard: ProjectLiveActionGuard,
  defaultLiveActionDisabledReason: DEFAULT_PROJECT_LIVE_ACTION_DISABLED_REASON,
  getLiveActionDisabledReason: getProjectLiveActionDisabledReason,
} as const;
