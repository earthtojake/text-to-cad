import { getPrNumber, isForkPr } from '@root/src/core/services/pull-requests/api';
import type { WorkspaceConfig } from './workspace-config';
import type { PresetContext, PresetOverrides, WorkspacePresetId } from './workspace-presets';

/**
 * Builds a `WorkspaceConfig` from a preset ID, context, and optional user overrides.
 *
 * This is a pure function with no side effects — safe to call in both the renderer
 * and the main process.
 *
 * Throws when required context fields are missing for the given preset (e.g. no PR
 * for `checkout-pr`).
 */
export function buildWorkspaceConfigFromPreset(
  presetId: WorkspacePresetId,
  context: PresetContext,
  overrides: PresetOverrides = {}
): WorkspaceConfig {
  switch (presetId) {
    case 'new-worktree': {
      const fromBranch = overrides.fromBranch ?? context.defaultBranch;
      if (!fromBranch) {
        throw new Error('new-worktree preset requires a fromBranch or defaultBranch in context');
      }
      const createBranch = overrides.createBranch ?? true;
      if (createBranch) {
        return {
          version: '2',
          git: {
            kind: 'create-branch',
            branchName: overrides.branchName ?? '',
            fromBranch,
            pushBranch: overrides.pushBranch ?? true,
          },
          workspace: { kind: 'new-worktree' },
        };
      }
      return {
        version: '2',
        git: { kind: 'use-branch', branchName: fromBranch.branch },
        workspace: { kind: 'new-worktree' },
      };
    }

    case 'repo-root': {
      const workspaceId = context.repositoryWorkspaceId;
      if (!workspaceId) {
        // Pre-mount fallback: no repositoryWorkspaceId yet.
        return {
          version: '2',
          git: { kind: 'none' },
          workspace: { kind: 'new-worktree' },
        };
      }
      return {
        version: '2',
        git: { kind: 'none' },
        workspace: { kind: 'repository-instance', workspaceId },
      };
    }

    case 'use-existing': {
      const workspaceId = context.existingWorkspaceId ?? context.repositoryWorkspaceId;
      if (!workspaceId) {
        throw new Error(
          'use-existing preset requires existingWorkspaceId or repositoryWorkspaceId'
        );
      }
      return {
        version: '2',
        git: { kind: 'none' },
        workspace: { kind: 'repository-instance', workspaceId },
      };
    }

    case 'checkout-pr': {
      const pr = context.pr;
      if (!pr) throw new Error('checkout-pr preset requires a PR in context');
      const prNumber = getPrNumber(pr) ?? 0;
      return {
        version: '2',
        git: {
          kind: 'pr-branch',
          prUrl: pr.url,
          prNumber,
          headBranch: pr.headRefName,
          headRepositoryUrl: pr.headRepositoryUrl,
          isFork: isForkPr(pr),
        },
        workspace: { kind: 'new-worktree' },
      };
    }

    case 'pr-new-branch': {
      const pr = context.pr;
      if (!pr) throw new Error('pr-new-branch preset requires a PR in context');
      const prNumber = getPrNumber(pr) ?? 0;
      return {
        version: '2',
        git: {
          kind: 'pr-branch',
          prUrl: pr.url,
          prNumber,
          headBranch: pr.headRefName,
          headRepositoryUrl: pr.headRepositoryUrl,
          isFork: isForkPr(pr),
          taskBranch: overrides.taskBranch ?? overrides.branchName ?? '',
          pushBranch: overrides.pushBranch ?? true,
        },
        workspace: { kind: 'new-worktree' },
      };
    }
  }
}
