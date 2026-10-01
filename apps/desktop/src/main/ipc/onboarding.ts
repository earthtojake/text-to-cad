/**
 * Handlers for `onboarding.*` (src/shared/ipc/onboarding.ts).
 */
import type { IpcHandlers } from "../../shared/ipc";
import type { onboardingContract } from "../../shared/ipc/onboarding";
import { createSampleProject, onboardingEnabled } from "../onboarding";
import { IpcError, type IpcContext } from "./register";

export const onboardingHandlers = {
  onboarding: {
    status: () => ({ enabled: onboardingEnabled() }),
    createSample: () => {
      try {
        return { path: createSampleProject() };
      } catch (error) {
        throw new IpcError(error instanceof Error ? error.message : String(error));
      }
    },
  },
} satisfies IpcHandlers<typeof onboardingContract, IpcContext>;
