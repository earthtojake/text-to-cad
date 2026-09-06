import { toast } from '@emdash/ui/react/primitives';
import { reaction } from 'mobx';
import { useEffect, useRef } from 'react';
import { getBrowserClient } from '@core/features/browser/api/browser/client';
import type { ConversationManagerStore } from '@core/features/conversations/api/browser/conversation-manager';
import { openFile } from '@core/features/workbench/api/browser/open-file';
import { resolveWorkspacePath } from '@core/features/workspaces/api/browser/workspace-path';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { CAD_VALIDATION_WIRE_TIMEOUT_MS } from '../api/cad-validation';
import { CAD_ARTIFACT_REVEAL_SETTLE_MS, startCadArtifactPolling } from './cad-artifact-poller';
import { cadTurnLedger } from './cad-turn-ledger';

export type CadArtifactRevealPlan = { open: string | null; announce: string[] };

/**
 * Decide what to do with model artifacts that appeared during a turn. With no
 * CAD tab open, the newest model (prefer STEP) opens in a preview tab. That
 * tab follows completed parts until the user pins it or selects another tab.
 * Existing pinned viewers remain under the user's control.
 */
export function planCadArtifactReveal(input: {
  newPaths: readonly string[];
  hasOpenCadTab: boolean;
  followingBuild?: boolean;
}): CadArtifactRevealPlan {
  const paths = [...new Set(input.newPaths)];
  if (paths.length === 0) return { open: null, announce: [] };
  if (input.hasOpenCadTab && !input.followingBuild) return { open: null, announce: paths };
  const preferred =
    [...paths].reverse().find((path) => /\.(?:step|stp)$/i.test(path)) ?? paths.at(-1)!;
  return { open: preferred, announce: paths.filter((path) => path !== preferred) };
}

type RevealTask = {
  projectId: string;
  taskId: string;
  workspace?: { path: string; sshConnectionId?: string } | null;
  paneLayout: {
    groups: ReadonlyArray<{
      pane: {
        resolvedTabs: ReadonlyArray<{
          kind: string;
          isActive?: boolean;
          isPreview?: boolean;
          resource?: object;
        }>;
      };
    }>;
  };
};

const statusSnapshot = (conversations: ConversationManagerStore) =>
  [...conversations.conversations.entries()].map(([id, store]) => [id, store.status] as const);

/**
 * Feed every conversation manager's status transitions into the ledger for as
 * long as the app lives: the task view that reveals models comes and goes with
 * navigation and pane changes, but the agents keep working underneath it.
 */
const watchedManagers = new WeakSet<ConversationManagerStore>();
function watchTurns(conversations: ConversationManagerStore): void {
  if (watchedManagers.has(conversations)) return;
  watchedManagers.add(conversations);
  cadTurnLedger.seed(statusSnapshot(conversations));
  reaction(
    () => statusSnapshot(conversations),
    (current, previous) => cadTurnLedger.apply(current, previous)
  );
}

/** Artifacts already revealed per workspace, so a remount never reopens the same model. */
const revealedPaths = new Map<string, Set<string>>();

/** Reveal settled output during active turns; the canonical viewer follows subsequent revisions. */
export function useCadArtifactReveal(
  task: RevealTask,
  conversations: ConversationManagerStore,
  isTrackedArtifact: (relativePath: string) => boolean
): void {
  const workspacePath = task.workspace?.path;
  const connectionId = task.workspace?.sshConnectionId;
  const { projectId, taskId, paneLayout } = task;
  const preview = useRef<{
    taskId: string;
    workspace: string;
    path: string;
    stopped: boolean;
  } | null>(null);

  useEffect(() => {
    // The CAD Viewer serves local directories only; remote workspaces have no viewer to reveal into.
    if (!workspacePath || connectionId) return;
    if (preview.current?.taskId !== taskId || preview.current.workspace !== workspacePath) {
      preview.current = null;
    }
    watchTurns(conversations);
    const revealed = revealedPaths.get(workspacePath) ?? new Set<string>();
    revealedPaths.set(workspacePath, revealed);

    const open = (relativePath: string, asPreview = false) =>
      openFile(hostFileRefFromNativePath(resolveWorkspacePath(workspacePath, relativePath)), {
        context: { projectId, taskId },
        target: 'artifact',
        preview: asPreview,
      });

    // A pinned, closed, or manually deselected preview must stay put, even if
    // the user later returns to it. Focusing the conversation doesn't stop it.
    const stopFollowing = reaction(
      () =>
        paneLayout.groups.some(({ pane }) =>
          pane.resolvedTabs.some(
            (tab) =>
              tab.kind === 'cad' &&
              tab.isActive &&
              tab.isPreview &&
              tab.resource &&
              'path' in tab.resource &&
              tab.resource.path === preview.current?.path
          )
        ),
      (stillFollowing) => {
        if (!stillFollowing && preview.current?.workspace === workspacePath) {
          preview.current.stopped = true;
        }
      }
    );

    const reveal = async (sinceMs: number, isDisposed: () => boolean): Promise<boolean> => {
      const client = await getBrowserClient();
      const result = await client.listCadArtifacts({ workspacePath, sinceMs });
      if (!result.success) throw new Error(result.error);
      if (isDisposed()) return false;
      let settled = true;
      const fresh: string[] = [];
      for (const { path, mtimeMs } of result.artifacts) {
        if (revealed.has(path) || isTrackedArtifact(path)) continue;
        if (Date.now() - mtimeMs < CAD_ARTIFACT_REVEAL_SETTLE_MS) {
          settled = false;
          continue;
        }
        if (/\.(?:step|stp)$/i.test(path)) {
          const validation = await client.validateCadModel(
            { workspacePath, filePath: path },
            { timeoutMs: CAD_VALIDATION_WIRE_TIMEOUT_MS }
          );
          if (isDisposed()) return false;
          if (!validation.success) continue;
        }
        fresh.push(path);
      }
      if (isDisposed()) return false;
      const hasOpenCadTab = paneLayout.groups.some(({ pane }) =>
        pane.resolvedTabs.some((tab) => tab.kind === 'cad')
      );
      const followingBuild = Boolean(
        preview.current?.workspace === workspacePath && !preview.current.stopped
      );
      const plan = planCadArtifactReveal({
        newPaths: fresh,
        hasOpenCadTab: hasOpenCadTab || preview.current?.stopped === true,
        followingBuild,
      });
      if (plan.open) {
        const path = plan.open;
        const previous = preview.current;
        preview.current = {
          taskId,
          workspace: workspacePath,
          path: resolveWorkspacePath(workspacePath, path),
          stopped: false,
        };
        if (open(path, true)) {
          revealed.add(path);
          if (!followingBuild) {
            toast.info('Live CAD preview', {
              description: 'Completed parts appear as they finish. Pin the tab to keep this view.',
              action: { label: 'Keep this view', onClick: () => open(path) },
            });
          }
        } else {
          preview.current = previous;
          settled = false;
        }
      }
      if (isDisposed()) return false;
      for (const path of plan.announce) {
        revealed.add(path);
        toast.info(`New CAD artifact: ${path.split('/').pop() ?? path}`, {
          description: path,
          duration: 10_000,
          action: { label: 'Open', onClick: () => open(path) },
        });
      }
      return settled;
    };

    const stopPolling = startCadArtifactPolling({
      ledger: cadTurnLedger,
      conversationIds: () => conversations.conversations.keys(),
      scan: reveal,
    });
    return () => {
      stopPolling();
      stopFollowing();
    };
  }, [
    connectionId,
    conversations,
    isTrackedArtifact,
    paneLayout,
    projectId,
    taskId,
    workspacePath,
  ]);
}
