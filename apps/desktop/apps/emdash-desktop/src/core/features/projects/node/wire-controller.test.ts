import { ok } from '@emdash/shared';
import { createScope } from '@emdash/shared/concurrency';
import { waitFor } from '@emdash/shared/testing';
import { cell, observe, remote, snapshot, whenReady } from '@emdash/wire/state';
import { createTestWire } from '@emdash/wire/testing';
import { describe, expect, it, vi } from 'vitest';
import { projectsWireContract, type ProjectAttachmentState } from '@core/features/projects/api';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import type { ProjectOperationDependencies } from './controller';
import { createProjectsWireController } from './wire-controller';

describe('Projects Wire attachments', () => {
  it('does not expose renderer-driven Project opening', () => {
    expect(projectsWireContract).not.toHaveProperty('openProject');
  });

  it('leases tracked attachment state and forwards recovery through Projects ownership', async () => {
    const state = cell<ProjectAttachmentState>({
      kind: 'attached',
      establishedHostGeneration: 3,
    });
    let leases = 0;
    const recover = vi.fn(async () => ok());
    const projects = {
      track: vi.fn((_projectId, owner) => {
        leases += 1;
        owner.add(() => {
          leases -= 1;
        });
        return state;
      }),
      recover,
    } as unknown as ProjectAttachmentManager;
    const controller = createProjectsWireController({
      projects,
    } as unknown as ProjectOperationDependencies);
    const wire = createTestWire(projectsWireContract, controller.impl);
    const scope = createScope({ label: 'projects-attachments-wire-test' });
    const attachments = remote(projectsWireContract.attachments, wire.client.attachments, {
      scope,
      lingerMs: 0,
    });
    const member = attachments({ projectId: 'project-1' });
    observe(member.states.state, () => {}, { scope, immediate: true });

    expect((await whenReady(member.states.state, { scope })).value).toEqual({
      kind: 'attached',
      establishedHostGeneration: 3,
    });
    expect(snapshot(member.states.state).value).toEqual({
      kind: 'attached',
      establishedHostGeneration: 3,
    });
    expect(leases).toBe(1);

    await expect(wire.client.recoverAttachment({ projectId: 'project-1' })).resolves.toEqual(ok());
    expect(recover).toHaveBeenCalledWith('project-1');

    await scope.dispose();
    expect(leases).toBe(1);

    const reconnectedScope = createScope({ label: 'projects-attachments-wire-reconnect-test' });
    const reconnectedAttachments = remote(
      projectsWireContract.attachments,
      wire.client.attachments,
      {
        scope: reconnectedScope,
        lingerMs: 0,
      }
    );
    const reconnectedMember = reconnectedAttachments({ projectId: 'project-1' });
    observe(reconnectedMember.states.state, () => {}, {
      scope: reconnectedScope,
      immediate: true,
    });
    await whenReady(reconnectedMember.states.state, { scope: reconnectedScope });

    expect(projects.track).toHaveBeenCalledOnce();
    expect(leases).toBe(1);

    await reconnectedScope.dispose();
    await wire.dispose();
    await controller.dispose();
    await waitFor(() => leases === 0);
  });
});
