import {
  SteppedLoader,
  SteppedLoaderProgress,
  type SteppedLoaderProps,
} from '@emdash/ui/react/components';
import { Button } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import type { ReactNode } from 'react';
import {
  type ProjectCreationStage,
  type UnregisteredProject,
} from '@core/features/projects/api/browser/stores/project';
import { getProjectManagerStore } from '@core/features/projects/api/browser/stores/project-selectors';
import { homeViewDef } from '@core/features/workbench/contributions/views';
import { useNavigate } from '@core/primitives/navigation/browser/navigation-hooks';

const STAGE_LABELS: Record<ProjectCreationStage, string> = {
  'creating-repo': 'Creating repository',
  cloning: 'Cloning repository',
  registering: 'Registering project',
};

const STAGES_BY_MODE: Record<'pick' | 'clone' | 'new', ProjectCreationStage[]> = {
  pick: ['registering'],
  clone: ['cloning', 'registering'],
  new: ['creating-repo', 'cloning', 'registering'],
};

export const PendingProjectStatus = observer(function PendingProjectStatus({
  project,
}: {
  project: UnregisteredProject;
}) {
  const { navigate } = useNavigate();
  const isError = project.creation.kind === 'failed';
  const manager = getProjectManagerStore();
  const loader = projectToSteppedLoader(project);

  const handleDismiss = () => {
    manager.removeUnregisteredProject(project.id);
    navigate(homeViewDef());
  };

  const handleCancel = () => {
    manager.cancelProjectCreation(project.id);
  };

  const actions = isError ? (
    <Button size="sm" variant="ghost" onClick={handleDismiss}>
      Dismiss
    </Button>
  ) : project.creation.kind === 'running' && project.creation.stage === 'cloning' ? (
    <Button size="sm" variant="ghost" onClick={handleCancel}>
      Cancel
    </Button>
  ) : undefined;

  return (
    <div className="flex min-w-0 flex-1 flex-col items-center justify-center gap-4 p-8">
      <div className="flex h-64 w-full max-w-md min-w-0">
        <SteppedLoader
          className="flex-1"
          steps={loader.steps}
          activeStepId={loader.activeStepId}
          status={loader.status}
          actions={actions}
        />
      </div>
      {isError && (
        <p className="max-w-full text-sm wrap-break-word text-foreground-destructive">
          {project.creation.kind === 'failed'
            ? project.creation.message
            : 'Project creation failed'}
        </p>
      )}
    </div>
  );
});

function projectToSteppedLoader(
  project: UnregisteredProject
): Pick<SteppedLoaderProps, 'steps' | 'activeStepId' | 'status'> {
  const stages = STAGES_BY_MODE[project.mode];
  const activeStepId = project.creation.stage;
  const activeChildren = progressChildren(project);
  return {
    steps: stages.map((stage) => ({
      id: stage,
      name: STAGE_LABELS[stage],
      children: stage === activeStepId ? activeChildren : undefined,
    })),
    activeStepId,
    status: project.creation.kind === 'failed' ? 'error' : 'loading',
  };
}

function progressChildren(project: UnregisteredProject): ReactNode {
  if (project.creation.kind === 'failed' || project.creation.progressPercent === undefined) {
    return undefined;
  }

  const percent = Math.max(0, Math.min(100, Math.round(project.creation.progressPercent)));
  const label = STAGE_LABELS[project.creation.stage];
  return (
    <SteppedLoaderProgress
      percent={percent}
      leftLabel={project.creation.progressMessage ?? label}
      rightLabel={`${percent}%`}
      aria-label={label}
    />
  );
}
