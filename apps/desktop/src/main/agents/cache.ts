/**
 * The detector's last table, kept in the settings table between launches.
 *
 * A launch's first `agents.list` used to wait on the login shell and every
 * `--version` (0.5–2 s), and the new-session chips waited with it. What the
 * last launch found is nearly always what this one will, so the detector
 * answers with it at once and lets the probe correct it (`AgentDetector.listWithin`).
 *
 * The rows carry the registry (install commands, adapter pins), so a table
 * from another build of the app is not trusted: the version is stored with it
 * and must match, and every provider must be in it, or the cache reads as empty.
 */
import { z } from "zod";

import { AgentStatusSchema, type AgentStatus } from "../../shared/agents";
import type { AgentsCache } from "./detect";
import { AGENT_PROVIDERS } from "./registry";

const StoredSchema = z.object({ version: z.string(), statuses: z.array(AgentStatusSchema) });

/** The storage, as `settings` in `../db/repositories` offers it. */
export type AgentsCacheStore = { agentsCache(): unknown; setAgentsCache(value: unknown): void };

/** `version` is a function because the app's version is asked of Electron, which a unit test has none of. */
export function settingsAgentsCache(store: AgentsCacheStore, version: () => string): AgentsCache {
  return {
    read() {
      const stored = StoredSchema.safeParse(store.agentsCache());
      if (!stored.success || stored.data.version !== version()) {
        return null;
      }
      const ids = new Set(stored.data.statuses.map((status) => status.id));
      return AGENT_PROVIDERS.every((provider) => ids.has(provider.id)) ? stored.data.statuses : null;
    },
    write(statuses: AgentStatus[]) {
      store.setAgentsCache({ version: version(), statuses });
    },
  };
}
