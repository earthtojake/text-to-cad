import type { WorkspacePlacementResolver } from '@core/features/workspaces/api/node/placement/workspace-placement-resolver';
import type { ResolveRepositoryDestinationParams } from '@core/primitives/projects/api';

export async function resolveRepositoryDestination(
  placement: WorkspacePlacementResolver,
  input: ResolveRepositoryDestinationParams
) {
  return placement.resolveRepositoryDestination(input.host, input.name, input.chosenDir);
}
