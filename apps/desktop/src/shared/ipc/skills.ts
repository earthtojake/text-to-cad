/**
 * `skills.info`: the skills root every session in this app is handed — where
 * it is on disk and what it holds (plan §8, as revised).
 *
 * Read-only, and there is nothing to install: Hardcore materialises the
 * skills it ships under its own user-data directory and names that directory
 * in every `session/new`, so Settings can show what a session gets but has no
 * button to press. (This branch replaced `plugins.*`, which installed a
 * composed plugin into each agent's global configuration.)
 *
 * `invoke` comes from `./define`, not from `../ipc` — the contract imports this
 * module, so importing it back is a load-time cycle.
 */
import { z } from "zod";

import { invoke } from "./define";

export const SkillSummarySchema = z.object({
  /** The skill's directory name, which is what an agent loads it by. */
  name: z.string(),
  /** Its SKILL.md front matter's description, or empty. */
  description: z.string().default(""),
});
export type SkillSummary = z.infer<typeof SkillSummarySchema>;

export const SkillsInfoSchema = z.object({
  /**
   * `<userData>/skills/<appVersion>`, holding every skill twice — under
   * `.claude/skills/` and `.agents/skills/`, the two layouts the native
   * loaders read. Null when no skills were composed into the app
   * (`npm run build` has not run in a checkout).
   */
  root: z.string().nullable(),
  skills: z.array(SkillSummarySchema),
});
export type SkillsInfo = z.infer<typeof SkillsInfoSchema>;

export const skillsContract = {
  skills: {
    /** What every session is handed. */
    info: invoke(z.void(), SkillsInfoSchema),
  },
} as const;
