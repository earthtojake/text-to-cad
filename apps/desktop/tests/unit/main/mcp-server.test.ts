import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { afterEach, describe, expect, it } from "vitest";

// The server the agent talks to, from its source; the packaged app runs the
// esbuild bundle of the same file (scripts/build-mcp.mjs).
import { BRIDGE_ENV, createServer, httpBridge } from "../../../resources/hardcore-mcp/server.mjs";

type Call = { method: string; params: unknown };

/** A fake main: records what the server asked and answers what it is told to. */
function fakeBridge(answers: Record<string, unknown | ((params: unknown) => unknown)> = {}) {
  const calls: Call[] = [];
  const bridge = async (method: string, params: unknown) => {
    calls.push({ method, params });
    const answer = answers[method];
    if (answer instanceof Error) {
      throw answer;
    }
    return typeof answer === "function" ? (answer as (params: unknown) => unknown)(params) : (answer ?? { ok: true });
  };
  return { bridge, calls };
}

const clients: Client[] = [];
afterEach(async () => {
  for (const client of clients.splice(0)) {
    await client.close();
  }
});

const temps: string[] = [];
afterEach(() => {
  for (const dir of temps.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

/** A materialised skills root, in the layout this server reads. */
function skillsRoot(skills: Record<string, string>): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-mcp-skills-"));
  temps.push(root);
  for (const [name, description] of Object.entries(skills)) {
    const dir = path.join(root, ".claude", "skills", name);
    fs.mkdirSync(path.join(dir, "references"), { recursive: true });
    fs.writeFileSync(path.join(dir, "SKILL.md"), `---\nname: ${name}\ndescription: ${description}\n---\n\nbody\n`);
    fs.writeFileSync(path.join(dir, "references", "selectors.md"), "the references page\n");
  }
  return root;
}

async function connect(
  bridge: (method: string, params: unknown) => Promise<unknown>,
  options: { skillsRoot?: string | null } = {},
) {
  const server = createServer(bridge, { version: "9.9.9", cwd: "/proj", skillsRoot: options.skillsRoot ?? null });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);
  const client = new Client({ name: "test", version: "0" });
  await client.connect(clientTransport);
  clients.push(client);
  return client;
}

describe("the Hardcore MCP server", () => {
  it("lists its tools with descriptions written for an agent", async () => {
    const client = await connect(fakeBridge().bridge);
    const { tools } = await client.listTools();
    expect(tools.map((tool) => tool.name).sort()).toEqual(
      [
        "attach_snapshot",
        "list_open_tabs",
        "list_skills",
        "open_file",
        "open_url",
        "read_skill",
        "reveal",
        "viewer_state",
      ].sort(),
    );
    const openFile = tools.find((tool) => tool.name === "open_file")!;
    expect(openFile.description).toContain("never");
    expect(openFile.inputSchema).toMatchObject({ type: "object", required: ["path"] });
    // The path's description names the cwd, so a relative path has a meaning.
    expect(JSON.stringify(openFile.inputSchema)).toContain("/proj");
    expect(tools.find((tool) => tool.name === "list_open_tabs")!.inputSchema).toMatchObject({ type: "object" });
  });

  it("forwards open_file to the bridge and returns its answer as text", async () => {
    const fake = fakeBridge({ open_file: { opened: "STEP/bracket.step", renderer: "cad" } });
    const client = await connect(fake.bridge);
    const result = await client.callTool({ name: "open_file", arguments: { path: "STEP/bracket.step" } });
    expect(fake.calls).toEqual([{ method: "open_file", params: { path: "STEP/bracket.step" } }]);
    expect(result.isError).toBeFalsy();
    const [content] = result.content as Array<{ type: string; text?: string }>;
    expect(content!.type).toBe("text");
    expect(JSON.parse(content!.text!)).toEqual({ opened: "STEP/bracket.step", renderer: "cad" });
  });

  it("returns attach_snapshot as image content so the transcript shows it", async () => {
    const png = Buffer.from("not a real png").toString("base64");
    const fake = fakeBridge({ attach_snapshot: { path: "tmp/review.png", mimeType: "image/png", base64: png } });
    const client = await connect(fake.bridge);
    const result = await client.callTool({ name: "attach_snapshot", arguments: { path: "tmp/review.png" } });
    const content = result.content as Array<{ type: string; data?: string; mimeType?: string; text?: string }>;
    expect(content[0]).toEqual({ type: "image", data: png, mimeType: "image/png" });
    expect(content[1]!.text).toContain("tmp/review.png");
  });

  it("turns a bridge refusal into an error result rather than a protocol failure", async () => {
    const fake = fakeBridge({ open_file: new Error("STEP/x.step is outside the project") });
    const client = await connect(fake.bridge);
    const result = await client.callTool({ name: "open_file", arguments: { path: "STEP/x.step" } });
    expect(result.isError).toBe(true);
    expect((result.content as Array<{ text: string }>)[0]!.text).toContain("outside the project");
  });

  it("validates arguments before reaching the bridge", async () => {
    const fake = fakeBridge();
    const client = await connect(fake.bridge);
    const result = await client.callTool({ name: "open_url", arguments: { url: "not a url" } });
    expect(result.isError).toBe(true);
    expect(fake.calls).toEqual([]);
  });

  it("carries every tool through the same bridge call", async () => {
    const fake = fakeBridge({ list_open_tabs: { tabs: [] }, viewer_state: { file: null }, reveal: { revealed: "src" }, open_url: { opened: "https://x.y" } });
    const client = await connect(fake.bridge);
    await client.callTool({ name: "list_open_tabs", arguments: {} });
    await client.callTool({ name: "viewer_state", arguments: {} });
    await client.callTool({ name: "reveal", arguments: { path: "src" } });
    await client.callTool({ name: "open_url", arguments: { url: "https://x.y/" } });
    expect(fake.calls.map((call) => call.method)).toEqual(["list_open_tabs", "viewer_state", "reveal", "open_url"]);
  });
});

describe("httpBridge", () => {
  it("refuses to start without the environment Hardcore sets", () => {
    expect(() => httpBridge({})).toThrow(BRIDGE_ENV.url);
  });

  it("posts to <url>/rpc with the bearer token and unwraps the answer", async () => {
    const seen: Array<{ url: string; init: RequestInit }> = [];
    const realFetch = globalThis.fetch;
    globalThis.fetch = (async (url: string, init: RequestInit) => {
      seen.push({ url, init });
      return new Response(JSON.stringify({ ok: true, result: { opened: "a.step" } }), { status: 200 });
    }) as typeof fetch;
    try {
      const bridge = httpBridge({ [BRIDGE_ENV.url]: "http://127.0.0.1:1234", [BRIDGE_ENV.token]: "tok" });
      expect(await bridge("open_file", { path: "a.step" })).toEqual({ opened: "a.step" });
      expect(seen[0]!.url).toBe("http://127.0.0.1:1234/rpc");
      expect((seen[0]!.init.headers as Record<string, string>).authorization).toBe("Bearer tok");
      expect(JSON.parse(seen[0]!.init.body as string)).toEqual({ method: "open_file", params: { path: "a.step" } });

      globalThis.fetch = (async () => new Response(JSON.stringify({ ok: false, error: "no such file" }), { status: 200 })) as typeof fetch;
      await expect(bridge("open_file", { path: "b" })).rejects.toThrow("no such file");
    } finally {
      globalThis.fetch = realFetch;
    }
  });
});

describe("the skills tools", () => {
  it("lists what the app put on disk, and tells the agent to read cad first", async () => {
    const root = skillsRoot({ cad: "Make CAD.", "hardcore-app-use": "Use this app." });
    const client = await connect(fakeBridge().bridge, { skillsRoot: root });

    const tools = (await client.listTools()).tools;
    const list = tools.find((tool) => tool.name === "list_skills")!;
    expect(list.description).toMatch(/read `?cad`? before any CAD/i);
    expect(tools.find((tool) => tool.name === "read_skill")!.description).toContain("hardcore-app-use");

    const result = await client.callTool({ name: "list_skills", arguments: {} });
    expect(result.isError).toBeFalsy();
    const answer = JSON.parse((result.content as Array<{ text: string }>)[0]!.text);
    expect(answer.root).toBe(path.join(root, ".claude", "skills"));
    expect(answer.skills).toEqual([
      { name: "cad", description: "Make CAD." },
      { name: "hardcore-app-use", description: "Use this app." },
    ]);
  });

  it("reads a SKILL.md, and a file inside the skill", async () => {
    const root = skillsRoot({ cad: "Make CAD." });
    const client = await connect(fakeBridge().bridge, { skillsRoot: root });

    const skill = await client.callTool({ name: "read_skill", arguments: { name: "cad" } });
    const first = JSON.parse((skill.content as Array<{ text: string }>)[0]!.text);
    expect(first.path).toBe(path.join("cad", "SKILL.md"));
    expect(first.text).toContain("description: Make CAD.");

    const reference = await client.callTool({
      name: "read_skill",
      arguments: { name: "cad", path: "references/selectors.md" },
    });
    expect(JSON.parse((reference.content as Array<{ text: string }>)[0]!.text).text).toBe("the references page\n");
  });

  it("refuses a skill that does not exist, a path outside one, and a session with no root", async () => {
    const root = skillsRoot({ cad: "Make CAD." });
    const client = await connect(fakeBridge().bridge, { skillsRoot: root });

    const missing = await client.callTool({ name: "read_skill", arguments: { name: "nope" } });
    expect(missing.isError).toBe(true);
    expect((missing.content as Array<{ text: string }>)[0]!.text).toContain("list_skills");

    const escape = await client.callTool({
      name: "read_skill",
      arguments: { name: "cad", path: "../hardcore-app-use/SKILL.md" },
    });
    expect(escape.isError).toBe(true);

    const traversal = await client.callTool({ name: "read_skill", arguments: { name: "../..", path: "SKILL.md" } });
    expect(traversal.isError).toBe(true);

    const bare = await connect(fakeBridge().bridge, { skillsRoot: null });
    const listed = await bare.callTool({ name: "list_skills", arguments: {} });
    expect(listed.isError).toBe(true);
    expect((await bare.callTool({ name: "read_skill", arguments: { name: "cad" } })).isError).toBe(true);
  });
});
