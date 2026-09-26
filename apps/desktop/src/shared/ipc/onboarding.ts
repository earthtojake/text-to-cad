/**
 * `onboarding.*`: what the first-run flow needs from main.
 *
 * Whether the person has finished the welcome, dismissed the checklist or
 * opened the viewer is ordinary settings (`onboarding*` fields in
 * `SettingsSchema`). These two are the parts that are not settings: whether
 * this run shows onboarding at all, and the sample project on disk.
 */
import { z } from "zod";

import { invoke } from "./define";

export const OnboardingStatusSchema = z.object({
  /**
   * False under the test suites (`NODE_ENV=test`), whose fresh profiles would
   * otherwise open on the welcome instead of the screen they test.
   * `HARDCORE_ONBOARDING=1` turns it back on for the onboarding specs.
   */
  enabled: z.boolean(),
});
export type OnboardingStatus = z.infer<typeof OnboardingStatusSchema>;

export const onboardingContract = {
  onboarding: {
    status: invoke(z.void(), OnboardingStatusSchema),
    /**
     * Copies the bundled sample to `~/Documents/Hardcore Sample` (or reuses
     * the copy already there) and answers with its path.
     */
    createSample: invoke(z.void(), z.object({ path: z.string() })),
  },
} as const;
