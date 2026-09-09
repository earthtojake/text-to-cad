/**
 * The skills root every session is handed, read once per mount.
 *
 * Made at launch and never changed while the app runs (`skills.info`,
 * `src/main/cad/skills.ts`), and read-only — there is nothing to install — so
 * it is a hook around one IPC call rather than a store.
 */
import { useEffect, useState } from "react";

import type { SkillsInfo } from "@shared/ipc/skills";

export function useSkills(): SkillsInfo | null {
  const [info, setInfo] = useState<SkillsInfo | null>(null);

  useEffect(() => {
    let live = true;
    void window.hardcore.skills.info().then((next) => {
      if (live) {
        setInfo(next);
      }
    });
    return () => {
      live = false;
    };
  }, []);

  return info;
}
