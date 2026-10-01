/**
 * Handlers for `onboarding.*` (src/shared/ipc/onboarding.ts).
 */
import type { IpcHandlers } from "../../shared/ipc";
import type { onboardingContract } from "../../shared/ipc/onboarding";
import { projects } from "../db/repositories";
import { createSampleProject, onboardingEnabled } from "../onboarding";
import { IpcError, type IpcContext } from "./register";

export const onboardingHandlers = {
  onboarding: {
    status: () => ({ enabled: onboardingEnabled() }),
    createSample: () => {
      try {
        // A folder main chose, so `projects.get` answers for it — but not
        // selected from here: the welcome that asked selects it, and only if
        // the person did not go Back while it copied. A broadcast would switch
        // the folder behind a welcome they had already left.
        return projects.choose(createSampleProject());
      } catch (error) {
        throw new IpcError(error instanceof Error ? error.message : String(error));
      }
    },
  },
} satisfies IpcHandlers<typeof onboardingContract, IpcContext>;
