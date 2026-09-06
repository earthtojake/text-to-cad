import { mkdtemp, readFile, realpath, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { AcpClient, confineToCwd } from "@main/acp/client";
import { TerminalManager } from "@main/acp/terminals";
import type { SessionEvent } from "@shared/acp/types";

async function scratch() {
  return realpath(await mkdtemp(path.join(os.tmpdir(), "hardcore-client-")));
}

function client(cwd: string, approvalMode: "ask" | "approve-for-me" = "ask") {
  const events: SessionEvent[] = [];
  const changed: string[][] = [];
  const instance = new AcpClient({
    cwd,
    env: {},
    terminals: new TerminalManager(() => {
      throw new Error("no terminals in this test");
    }),
    dispatch: (event) => events.push(event),
    onFilesChanged: (paths) => changed.push(paths),
    approvalMode,
  });
  return { instance, events, changed };
}

const permission = {
  sessionId: "s",
  toolCall: { toolCallId: "c1", title: "Run ls", kind: "execute" as const, status: "pending" as const, rawInput: { command: "ls" } },
  options: [
    { optionId: "allow-once", name: "Yes", kind: "allow_once" as const },
    { optionId: "allow-always", name: "Always", kind: "allow_always" as const },
    { optionId: "reject", name: "No", kind: "reject_once" as const },
  ],
  _meta: { permission: { version: 1, title: "Run ls?", description: "Lists files." } },
};

describe("AcpClient permissions", () => {
  it("parks the request until the renderer answers, narrating both ends", async () => {
    const { instance, events } = client("/tmp");
    const answer = instance.requestPermission(permission);
    expect(events).toMatchObject([{ type: "permission/request", request: { requestId: "perm-1", title: "Run ls?", description: "Lists files." } }]);
    expect(instance.pendingPermissionIds).toEqual(["perm-1"]);
    expect(instance.respondPermission("perm-1", "allow-always")).toBe(true);
    expect(await answer).toEqual({ outcome: { outcome: "selected", optionId: "allow-always" } });
    expect(events.at(-1)).toMatchObject({ type: "permission/resolve", outcome: { state: "selected", optionId: "allow-always" } });
    expect(instance.respondPermission("perm-1", "allow-once")).toBe(false);
  });

  it("answers cancelled when the renderer cancels, and when the turn is cancelled", async () => {
    const { instance } = client("/tmp");
    const first = instance.requestPermission(permission);
    instance.respondPermission("perm-1", null);
    expect(await first).toEqual({ outcome: { outcome: "cancelled" } });
    const second = instance.requestPermission(permission);
    instance.cancelPendingPermissions();
    expect(await second).toEqual({ outcome: { outcome: "cancelled" } });
  });

  it("approve-for-me picks the allow_once option itself, but still asks when there is none", async () => {
    const { instance, events } = client("/tmp", "approve-for-me");
    expect(await instance.requestPermission(permission)).toEqual({ outcome: { outcome: "selected", optionId: "allow-once" } });
    expect(events.map((event) => event.type)).toEqual(["permission/request", "permission/resolve"]);

    const onlyAlways = { ...permission, options: permission.options.filter((o) => o.kind !== "allow_once") };
    const pending = instance.requestPermission(onlyAlways);
    expect(instance.pendingPermissionIds).toEqual(["perm-2"]);
    instance.respondPermission("perm-2", "reject");
    expect(await pending).toEqual({ outcome: { outcome: "selected", optionId: "reject" } });
  });

  it("can switch modes between requests", async () => {
    const { instance } = client("/tmp");
    instance.approvalMode = "approve-for-me";
    expect(await instance.requestPermission(permission)).toEqual({ outcome: { outcome: "selected", optionId: "allow-once" } });
  });
});

describe("AcpClient files", () => {
  it("reads whole files and line windows", async () => {
    const dir = await scratch();
    const file = path.join(dir, "a.txt");
    await writeFile(file, "one\ntwo\nthree\nfour\n");
    const { instance } = client(dir);
    expect((await instance.readTextFile({ sessionId: "s", path: file })).content).toBe("one\ntwo\nthree\nfour\n");
    expect((await instance.readTextFile({ sessionId: "s", path: file, line: 2, limit: 2 })).content).toBe("two\nthree");
    expect((await instance.readTextFile({ sessionId: "s", path: file, line: 4 })).content).toBe("four\n");
  });

  it("refuses relative paths", async () => {
    const { instance } = client(await scratch());
    await expect(instance.readTextFile({ sessionId: "s", path: "a.txt" })).rejects.toThrow(/absolute/);
  });

  it("writes inside the session directory, creating parents, and announces the path", async () => {
    const dir = await scratch();
    const { instance, changed } = client(dir);
    const target = path.join(dir, "deep", "er", "b.txt");
    await instance.writeTextFile({ sessionId: "s", path: target, content: "hello" });
    expect(await readFile(target, "utf8")).toBe("hello");
    expect(changed).toEqual([[target]]);
  });

  it("refuses to write outside the session directory, including through a symlink", async () => {
    const dir = await scratch();
    const outside = await scratch();
    const { instance } = client(dir);
    await expect(instance.writeTextFile({ sessionId: "s", path: path.join(outside, "x.txt"), content: "" })).rejects.toThrow(/outside/);
    await expect(instance.writeTextFile({ sessionId: "s", path: path.join(dir, "..", "escape.txt"), content: "" })).rejects.toThrow(/outside/);
    await symlink(outside, path.join(dir, "link"));
    await expect(instance.writeTextFile({ sessionId: "s", path: path.join(dir, "link", "y.txt"), content: "" })).rejects.toThrow(/link/);
  });

  it("confineToCwd answers the normalised path for an inside target", async () => {
    const dir = await scratch();
    expect(await confineToCwd(dir, path.join(dir, "sub", "..", "c.txt"))).toBe(path.join(dir, "c.txt"));
  });
});
