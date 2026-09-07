/**
 * `agentOptions.*` handlers: the cache of what each agent's sessions can be
 * configured with, and the defaults the next one starts at.
 *
 * The store itself is created beside the session manager (`./acp.ts`), which
 * owns the adapter the probe spawns; this file is only the contract's side of
 * it.
 */
import { agentOptions } from "./acp";
import { detector } from "./agents";
import type { IpcHandlers } from "../../shared/ipc";
import type { agentOptionsContract } from "../../shared/ipc/agent-options";
import type { IpcContext } from "./register";

export const agentOptionsHandlers = {
  agentOptions: {
    list: () => agentOptions.list(),
    // Deliberately not awaited: a probe spawns an adapter and can take a
    // couple of seconds, and the answer is a broadcast, not a return value.
    // The renderer asks and draws whatever arrives.
    probe: ({ agentId, projectId }) => {
      void agentOptions.ensure(agentId, projectId ?? null);
    },
    setDefaults: ({ agentId, model, effort }) =>
      agentOptions.setDefaults(agentId, {
        ...(model === undefined ? {} : { model }),
        ...(effort === undefined ? {} : { effort }),
      }),
  },
} satisfies IpcHandlers<typeof agentOptionsContract, IpcContext>;

// A provider that could not be probed — not installed, not signed in — is not
// asked again until something about it changes. An install or a login is
// exactly that, so the detector's next table clears the refusals and the
// new-session screen probes it the next time it is looked at.
detector.onChange(() => agentOptions.forgetFailures());

