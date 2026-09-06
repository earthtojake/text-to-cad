import { createEmitter } from '@emdash/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { projectViewDef } from '@core/features/projects/contributions/views';
import { homeViewDef } from '@core/features/workbench/contributions/views';
import type {
  NavigationEvent,
  NavigationStore,
} from '@core/primitives/navigation/browser/navigation-store';

const captureTelemetry = vi.hoisted(() => vi.fn());

vi.mock('@core/primitives/telemetry/browser/telemetry-client', () => ({
  captureTelemetry,
}));

const { wireNavigationTelemetry } = await import('./navigation-telemetry');

describe('wireNavigationTelemetry', () => {
  beforeEach(() => {
    captureTelemetry.mockClear();
  });

  it('observes traversals and restorations only when the view changes', () => {
    const onDidNavigate = createEmitter<NavigationEvent>();
    wireNavigationTelemetry({ onDidNavigate } as NavigationStore);
    const home = homeViewDef();
    const firstProject = projectViewDef({ projectId: 'p1' });
    const secondProject = projectViewDef({ projectId: 'p2' });

    onDidNavigate.emit({ from: home, to: firstProject, kind: 'traversal' });
    onDidNavigate.emit({
      from: firstProject,
      to: secondProject,
      kind: 'restoration',
    });
    onDidNavigate.emit({ from: secondProject, to: home, kind: 'restoration' });

    expect(captureTelemetry).toHaveBeenNthCalledWith(1, 'project_viewed', {
      from_view: 'home',
    });
    expect(captureTelemetry).toHaveBeenNthCalledWith(2, 'home_viewed', {
      from_view: 'project',
    });
    expect(captureTelemetry).toHaveBeenCalledTimes(2);
  });
});
