import { mkdtemp, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import { SessionConnection } from "@main/acp/connection";
import { spawnProcessTerminal } from "@main/acp/process-backend";
import { modeChoice } from "@shared/acp/options";
import { allToolCalls, lastAgentText } from "@shared/acp/reduce";

/**
 * The other shape ACP allows for the same decision. An agent can send its
 * modes as `modes` — switched by `session/set_mode` — or as a `mode`-category
 * config option switched by `session/set_config_option`. An adapter that sent
 * only the option used to get no mode chip at all, and the mode is the app's
 * one permission control. The fake agent's `--mode-option` sends no `modes`,
 * the same list as a config option.
 *
 * The chip that draws it is `modeChoice` (`tests/unit/shared/options.test.ts`)
 * and the dispatch is `SessionView`'s two branches; this is the wire under
 * them, against the real agent process.
 */

const FAKE_AGENT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "fake-agent", "index.mjs");
const open: SessionConnection[] = [];

afterEach(async () => {
  for (const connection of open.splice(0)) {
    connection.close();
    await connection.exited;
  }
});

async function connect() {
  const connection = new SessionConnection({
    sessionId: "mode-option",
    agentId: "fake",
    launch: { command: process.execPath, args: [FAKE_AGENT, "--mode-option"], env: {} },
    env: { PATH: process.env.PATH ?? "" },
    cwd: await realpath(await mkdtemp(path.join(os.tmpdir(), "text-to-cad-mode-option-"))),
    skillsRoot: null,
    preamble: null,
    spawnTerminal: spawnProcessTerminal,
  });
  open.push(connection);
  await connection.initialize();
  await connection.newSession();
  return connection;
}

describe("an agent that sends its modes as a config option", () => {
  it("gets the one mode chip, set through set_config_option", async () => {
    const connection = await connect();
    expect(connection.state.modes).toEqual([]);
    const choice = modeChoice(connection.state);
    expect(choice).toMatchObject({ source: "config_option", configId: "mode", currentModeId: "default" });
    expect(choice!.modes.map((mode) => mode.name)).toEqual(["Manual", "Plan", "Auto", "Full access"]);

    // Left where it starts, nothing is sent for the mode at all.
    await connection.prompt([{ type: "text", text: "applied" }]);
    expect(lastAgentText(connection.state)).toContain("in default");
    expect(lastAgentText(connection.state)).not.toContain("mode:");

    // Full access, through the option: the agent is on it, and a request Manual would have
    // shown is never made.
    await connection.setConfigOption(choice!.configId!, "full");
    expect(modeChoice(connection.state)?.currentModeId).toBe("full");
    const response = await connection.prompt([{ type: "text", text: "permission to run ls" }]);
    expect(response.stopReason).toBe("end_turn");
    expect(connection.state.pendingPermissions).toEqual([]);
    expect(allToolCalls(connection.state).at(-1)).toMatchObject({ status: "completed" });
    await connection.prompt([{ type: "text", text: "applied" }]);
    expect(lastAgentText(connection.state)).toContain("mode:full in full");
  });
});
