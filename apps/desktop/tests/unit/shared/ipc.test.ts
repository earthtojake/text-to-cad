import { describe, expect, it } from "vitest";
import { z } from "zod";

import {
  defineIpc,
  invoke,
  ipcChannels,
  ipcContract,
  ipcEvents,
  isInvokeDef,
} from "@shared/ipc";
import { UpdateStatusSchema } from "@shared/ipc/app";

describe("defineIpc", () => {
  it("flattens a nested contract into dotted channel names", () => {
    const contract = defineIpc({
      a: { b: invoke(z.void(), z.string()), c: invoke(z.number(), z.void()) },
      d: invoke(z.void(), z.void()),
    });
    expect(ipcChannels(contract).map(([name]) => name)).toEqual(["a.b", "a.c", "d"]);
  });

  it("tells leaves from branches", () => {
    expect(isInvokeDef(invoke(z.void(), z.void()))).toBe(true);
    expect(isInvokeDef({ nested: invoke(z.void(), z.void()) })).toBe(false);
    expect(isInvokeDef(null)).toBe(false);
  });
});

describe("the contract", () => {
  it("declares the P0 channels", () => {
    expect(ipcChannels(ipcContract).map(([name]) => name)).toEqual([
      "app.info",
      "app.updateStatus",
      "app.checkForUpdates",
      "app.downloadUpdate",
      "app.installUpdate",
      "projects.list",
      "projects.add",
      "projects.addPath",
      "projects.remove",
      "projects.rename",
      "sessions.list",
      "settings.get",
      "settings.set",
      "window.state",
      "shell.openExternal",
      "shell.showItemInFolder",
    ]);
  });

  it("validates requests, which is the whole reason the schemas are there", () => {
    const channels = Object.fromEntries(ipcChannels(ipcContract));
    const rename = channels["projects.rename"];
    expect(rename?.request.safeParse({ id: "p1", name: "Robot" }).success).toBe(true);
    // An empty name would rename a project to nothing at all.
    expect(rename?.request.safeParse({ id: "p1", name: "" }).success).toBe(false);
    expect(rename?.request.safeParse({ id: "p1" }).success).toBe(false);
  });

  it("keeps non-URLs out of openExternal before main even sees them", () => {
    const channels = Object.fromEntries(ipcChannels(ipcContract));
    const open = channels["shell.openExternal"];
    expect(open?.request.safeParse({ url: "https://example.com" }).success).toBe(true);
    expect(open?.request.safeParse({ url: "not a url" }).success).toBe(false);
  });
});

describe("the updater branch", () => {
  it("bounds the download percentage", () => {
    // A percentage the UI prints straight into a string, so the schema is where
    // electron-updater's float is refused rather than three files later.
    expect(UpdateStatusSchema.safeParse({ state: "downloading", percent: 42 }).success).toBe(true);
    expect(UpdateStatusSchema.safeParse({ state: "downloading", percent: 140 }).success).toBe(false);
  });

  it("has an honest state for a build with no feed", () => {
    // A development build must never be told to replace itself; `unsupported`
    // is how About says so instead of showing a dead Check button.
    expect(UpdateStatusSchema.safeParse({ state: "unsupported" }).success).toBe(true);
    expect(UpdateStatusSchema.safeParse({ state: "ready" }).success).toBe(false);
  });
});

describe("events", () => {
  it("gives every channel a payload schema", () => {
    for (const [channel, schema] of Object.entries(ipcEvents)) {
      expect(schema, channel).toBeInstanceOf(z.ZodType);
    }
  });

  it("names the ui commands the menu sends", () => {
    const command = ipcEvents["ui.command"];
    expect(command.safeParse({ command: "toggle-sidebar" }).success).toBe(true);
    expect(command.safeParse({ command: "explode" }).success).toBe(false);
  });
});
