import { err, ok } from '@emdash/shared';
import { describe, expect, it, vi } from 'vitest';
import { requireAttachedProjectOrThrow, withAttachedProject } from './attached-project';

describe('attached Project access', () => {
  it('runs fallible work with the attached provider', async () => {
    const project = { projectId: 'project-1' };
    const work = vi.fn(async () => ok('done'));

    await expect(
      withAttachedProject(
        { requireAttached: vi.fn(() => ok(project as never)) },
        project.projectId,
        work
      )
    ).resolves.toEqual(ok('done'));
    expect(work).toHaveBeenCalledWith(project);
  });

  it('returns the attachment error without running work', async () => {
    const attachmentError = { type: 'project-missing' as const, projectId: 'project-1' };
    const work = vi.fn(async () => ok('done'));

    await expect(
      withAttachedProject(
        { requireAttached: vi.fn(() => err(attachmentError)) },
        attachmentError.projectId,
        work
      )
    ).resolves.toEqual(err(attachmentError));
    expect(work).not.toHaveBeenCalled();
  });

  it('throws the attachment type by default and supports boundary-specific errors', () => {
    const attachmentError = { type: 'project-missing' as const, projectId: 'project-1' };
    const projects = { requireAttached: vi.fn(() => err(attachmentError)) };

    expect(() => requireAttachedProjectOrThrow(projects, attachmentError.projectId)).toThrow(
      'project-missing'
    );
    expect(() =>
      requireAttachedProjectOrThrow(
        projects,
        attachmentError.projectId,
        (error) => new Error(`Project attachment unavailable: ${error.type}`)
      )
    ).toThrow('Project attachment unavailable: project-missing');
  });
});
