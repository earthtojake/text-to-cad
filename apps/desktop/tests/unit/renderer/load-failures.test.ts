import { beforeEach, expect, it, vi } from "vitest";
import type { ClipboardPort, ViewerLoadFailure } from "@text-to-cad/ui/host";

import { createDesktopLoadFailures, loadFailurePrompt } from "@renderer/features/explorer/host/loadFailures";
import { createDesktopPromptContext } from "@renderer/features/explorer/host/promptContext";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { useRuntime } from "@renderer/state/runtime";
import { useSessions } from "@renderer/state/sessions";
import type { Project, Session } from "@shared/types";

const workspaceId = JSON.stringify(["desktop", "car", null]);
const failure: ViewerLoadFailure = {
  kind: "compile", file: "models/bracket.step", title: "Couldn’t prepare the model", blocking: true,
  reason: "NameError: name 'bracket' is not defined",
  details: "File: models/bracket.step\nOperation: preparing display assets\nNameError: name 'bracket' is not defined",
};
const clipboard = (): ClipboardPort => ({ writeText: vi.fn(async () => {}), readText: async () => "", writeImage: async () => {} });

beforeEach(() => {
  useProjects.setState({ activeId: "car", projects: [{ id: "car", path: "/car" }] as Project[] });
  useSessions.setState({ activeId: "first", sessions: [{ id: "first", projectId: "car", cwd: "/car" } as Session] });
  useComposer.setState({ drafts: {}, pendingFiles: {}, draftRoots: {}, acceptedContexts: {}, focusRequest: null, referenceLabels: {}, queues: {} });
});

it("a build failure names the CAD runtime, never a terminal or address, and offers the agent and the clipboard", () => {
  const recovery = createDesktopLoadFailures(createDesktopPromptContext("car", null, workspaceId, "first"), clipboard()).recover(failure)!;
  expect(recovery.message).toBe("The CAD runtime reported an error building “models/bracket.step”.");
  expect(`${recovery.message} ${recovery.recovery}`).not.toMatch(/terminal|address/);
  expect(recovery.actions?.map(action => action.label)).toEqual(["Ask the agent to fix", "Copy details"]);
});

it("a build failure on a runtime with a CAD kernel warning quotes the warning, in cadgen's words, before the next step", () => {
  const words = "ValueError: op memo requires the cadquery-ocp-novtk distribution for persistent reuse";
  useRuntime.setState({ status: { state: "ready", python: "/py", source: "override", cadgenVersion: "9.9.9", viewerBuilt: true, log: null, kernel: { state: "unsupported", message: words } } });
  try {
    const recovery = createDesktopLoadFailures(createDesktopPromptContext("car", null, workspaceId, "first"), clipboard()).recover(failure)!;
    expect(recovery.recovery).toBe(`The CAD runtime's kernel is unsupported, which can stop a STEP build: ${words}. Ask the agent to fix the source, or copy the details.`);
  } finally {
    useRuntime.setState({ status: null });
  }
});

it("a build failure on a runtime whose kernel check timed out asks for Repair, not a source fix", () => {
  useRuntime.setState({ status: { state: "ready", python: "/py", source: "override", cadgenVersion: "9.9.9", viewerBuilt: true, log: null, kernel: { state: "timeout", message: "timed out after 90 s" } } });
  try {
    const recovery = createDesktopLoadFailures(createDesktopPromptContext("car", null, workspaceId, "first"), clipboard()).recover(failure)!;
    expect(recovery.recovery).toBe("The CAD runtime's kernel check did not finish (timed out after 90 s). Run Repair in Settings › About, then Try again; or copy the details.");
    expect(recovery.recovery).not.toMatch(/fix the source/);
  } finally {
    useRuntime.setState({ status: null });
  }
});

it("Ask the agent to fix delivers the diagnostic to the session's prompt; Copy details copies it", async () => {
  const board = clipboard();
  const [ask, copy] = createDesktopLoadFailures(createDesktopPromptContext("car", null, workspaceId, "first"), board).recover(failure)!.actions!;
  expect(await ask!.run()).toBe("Added to the prompt.");
  const draft = useComposer.getState().drafts.first!;
  expect(draft).toContain("models/bracket.step");
  expect(draft).toContain("NameError: name 'bracket' is not defined");
  expect(await copy!.run()).toBe("Copied.");
  expect(board.writeText).toHaveBeenCalledWith(failure.details);
});

it("Ask the agent to fix is unavailable, with the destination's reason, while the session can't take a prompt", () => {
  useSessions.setState({ sessions: [] });
  const [ask, copy] = createDesktopLoadFailures(createDesktopPromptContext("car", null, workspaceId, "first"), clipboard()).recover(failure)!.actions!;
  expect(ask).toMatchObject({ disabled: true, reason: "This tab's session is no longer active." });
  expect(copy!.disabled).toBeUndefined();
});

it("an empty mesh and a failed edit are not build errors: the card keeps its words and the agent is asked the right thing", async () => {
  const host = createDesktopLoadFailures(createDesktopPromptContext("car", null, workspaceId, "first"), clipboard());
  const empty: ViewerLoadFailure = { kind: "empty", file: "meshes/panel.stl", title: "No geometry to display", blocking: true };
  const edit: ViewerLoadFailure = { kind: "edit", file: "models/bracket.step", title: "Couldn’t update the model", blocking: false,
    reason: "Fillet radius is too large", details: "File: models/bracket.step\nOperation: updating the model\nFillet radius is too large" };
  for (const alert of [empty, edit]) {
    const recovery = host.recover(alert)!;
    expect(recovery.message).toBeUndefined();
    expect(recovery.recovery).toBeUndefined();
    expect(loadFailurePrompt(alert)).not.toMatch(/runtime could not build|Fix the source/);
    expect(loadFailurePrompt(alert)).toContain(alert.file);
  }
  expect(loadFailurePrompt(empty)).toMatch(/no geometry/);
  expect(loadFailurePrompt(edit)).toMatch(/live edit of “models\/bracket.step” failed[\s\S]*Fillet radius is too large/);
  const [ask] = host.recover(edit)!.actions!;
  expect(await ask!.run()).toBe("Added to the prompt.");
  expect(useComposer.getState().drafts.first).toContain("A live edit of “models/bracket.step” failed");
});
