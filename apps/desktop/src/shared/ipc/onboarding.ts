/**
 * `onboarding.*`: what the first-run flow needs from main.
 *
 * Whether the person has finished the welcome, dismissed the checklist or
 * opened the viewer is ordinary settings (`onboarding*` fields in
 * `SettingsSchema`). These two are the parts that are not settings: whether
 * this run shows onboarding at all, and the sample project on disk.
 */
import { z } from "zod";

import { ProjectSchema } from "../types";
import { invoke } from "./define";

export const OnboardingStatusSchema = z.object({
  /**
   * False under the test suites (`NODE_ENV=test`), whose fresh profiles would
   * otherwise open on the welcome instead of the screen they test.
   * `TEXT_TO_CAD_ONBOARDING=1` turns it back on for a test that wants the welcome.
   */
  enabled: z.boolean(),
});
export type OnboardingStatus = z.infer<typeof OnboardingStatusSchema>;

export const onboardingContract = {
  onboarding: {
    status: invoke(z.void(), OnboardingStatusSchema),
    /**
     * Copies the bundled sample to `~/Documents/text-to-cad Sample` (or reuses
     * the copy already there), makes it a folder main chose, and answers with
     * the project. It broadcasts nothing: the welcome selects the answer
     * itself, and not at all if the person went Back while it copied. Never a
     * path for the renderer to hand back: no channel takes one.
     */
    createSample: invoke(z.void(), ProjectSchema),
  },
} as const;
