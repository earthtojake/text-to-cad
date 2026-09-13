import { isDeepEqual, err, type Result } from '@emdash/shared';
import { and, eq, isNull } from 'drizzle-orm';
import {
  createWorkspaceRegistry,
  workspaceRegistryTable as workspaces,
  type WorkspaceClaimError,
  type WorkspaceClaimInput,
} from '@core/features/workspaces/api/node/registry';
import type { AppDb } from '@core/services/app-db/node/db';
import { projects, tasks, type WorkspaceRow } from '@core/services/app-db/node/schema';

export type WorkspaceIdentityTranslationError =
  | WorkspaceClaimError
  | { type: 'source-workspace-missing'; sourceId: string }
  | { type: 'workspace-annotation-conflict'; workspaceId: string; field: 'config' }
  | {
      type: 'workspace-binding-conflict';
      sourceId: string;
      canonicalId: string;
      binding: 'project';
    };

/**
 * Applies an explicitly authorized old-id -> Host-canonical-id transition. Its only
 * callers are the one-time production backfill and Project repository initialization after
 * createWorkspace resolves the Project path to a different canonical record.
 *
 * The old mirror row must still match the caller's expected Host and path. All desktop
 * bindings move in one transaction; the obsolete row remains untracked as history and
 * its desktop-owned config moves to the canonical row. Claim and Observe never call
 * this path-based translation seam.
 */
export function translateWorkspaceIdentity(
  db: AppDb,
  sourceId: string,
  input: WorkspaceClaimInput,
  expectedSourcePath: string
): Result<WorkspaceRow, WorkspaceIdentityTranslationError> {
  if (sourceId === input.record.id) {
    throw new Error('Workspace identity translation requires different source and canonical ids');
  }

  const registry = createWorkspaceRegistry(db);
  try {
    return db.transaction((tx) => {
      const source = tx.select().from(workspaces).where(eq(workspaces.id, sourceId)).limit(1).get();
      if (!source) return err({ type: 'source-workspace-missing', sourceId });
      if (source.deletionTombstone !== null) {
        return err({ type: 'workspace-tombstoned', workspaceId: sourceId });
      }
      if (
        source.untrackedAt !== null ||
        source.location !== input.host.location ||
        source.sshConnectionId !== input.host.sshConnectionId ||
        source.path !== expectedSourcePath
      ) {
        return identityConflict(input, sourceId);
      }

      const canonical = tx
        .select()
        .from(workspaces)
        .where(eq(workspaces.id, input.record.id))
        .limit(1)
        .get();
      if (canonical?.deletionTombstone !== null && canonical?.deletionTombstone !== undefined) {
        return err({ type: 'workspace-tombstoned', workspaceId: input.record.id });
      }
      if (
        canonical &&
        (canonical.location !== input.host.location ||
          canonical.sshConnectionId !== input.host.sshConnectionId)
      ) {
        return identityConflict(input, canonical.id);
      }

      const pathOwner = registry.findLiveByPath(
        input.host.location,
        input.host.sshConnectionId,
        input.record.path,
        tx
      );
      if (pathOwner && pathOwner.id !== sourceId && pathOwner.id !== input.record.id) {
        return identityConflict(input, pathOwner.id);
      }

      const sourceConfig = source.config;
      const canonicalConfig = canonical?.config ?? input.config ?? null;
      if (
        sourceConfig !== null &&
        canonicalConfig !== null &&
        !isDeepEqual(sourceConfig, canonicalConfig)
      ) {
        return err({
          type: 'workspace-annotation-conflict',
          workspaceId: input.record.id,
          field: 'config',
        });
      }

      const sourceProject = tx
        .select({ id: projects.id })
        .from(projects)
        .where(and(eq(projects.repositoryWorkspaceId, sourceId), isNull(projects.deletedAt)))
        .limit(1)
        .get();
      const canonicalProject = tx
        .select({ id: projects.id })
        .from(projects)
        .where(and(eq(projects.repositoryWorkspaceId, input.record.id), isNull(projects.deletedAt)))
        .limit(1)
        .get();
      if (sourceProject && canonicalProject && sourceProject.id !== canonicalProject.id) {
        return err({
          type: 'workspace-binding-conflict',
          sourceId,
          canonicalId: input.record.id,
          binding: 'project',
        });
      }

      const changed = registry.untrack([sourceId], new Date().toISOString(), undefined, tx);
      if (changed !== 1) {
        throw new TranslationAborted({ type: 'source-workspace-missing', sourceId });
      }
      registry.updateConfig(sourceId, null, tx);
      const claimed = registry.claim(
        { ...input, config: canonicalConfig ?? sourceConfig ?? undefined },
        tx
      );
      if (!claimed.success) throw new TranslationAborted(claimed.error);

      tx.update(projects)
        .set({ repositoryWorkspaceId: input.record.id, updatedAt: new Date().toISOString() })
        .where(eq(projects.repositoryWorkspaceId, sourceId))
        .run();
      tx.update(tasks)
        .set({ workspaceId: input.record.id, updatedAt: new Date().toISOString() })
        .where(eq(tasks.workspaceId, sourceId))
        .run();
      tx.update(workspaces)
        .set({ parentId: input.record.id, updatedAt: new Date().toISOString() })
        .where(eq(workspaces.parentId, sourceId))
        .run();
      return claimed;
    });
  } catch (error) {
    if (error instanceof TranslationAborted) return err(error.error);
    throw error;
  }
}

function identityConflict(
  input: WorkspaceClaimInput,
  conflictingId: string
): Result<never, WorkspaceIdentityTranslationError> {
  return err({
    type: 'workspace-identity-conflict',
    path: input.record.path,
    incomingId: input.record.id,
    conflictingId,
  });
}

class TranslationAborted extends Error {
  constructor(readonly error: WorkspaceIdentityTranslationError) {
    super(error.type);
  }
}
