/**
 * `skills.info` handler: the materialised skills root and what it holds
 * (`src/main/integrations/skills.ts`). One read, no side effects — the root is made at
 * launch, not on demand.
 */
import type { IpcHandlers } from "../../shared/ipc";
import type { skillsContract } from "../../shared/ipc/skills";
import { skillsRoot, skillSummaries } from "../integrations";
import type { IpcContext } from "./register";

export const skillsHandlers = {
  skills: {
    info: () => ({ root: skillsRoot(), skills: skillSummaries() }),
  },
} satisfies IpcHandlers<typeof skillsContract, IpcContext>;
