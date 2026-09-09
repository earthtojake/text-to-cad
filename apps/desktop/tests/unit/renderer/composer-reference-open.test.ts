import { beforeEach, expect, it, vi } from "vitest";

import { openComposerReference } from "@renderer/features/session/composer/ReferenceScope";
import { useExplorer } from "@renderer/state/explorer";
import type { FileTab } from "@shared/types";

const openFile = vi.fn(() => ({ id: "worktree-car" }) as FileTab);
const selectCadReference = vi.fn();
const scope = { projectId: "car", root: "/worktrees/wider-wheel" };

beforeEach(() => {
  vi.clearAllMocks();
  useExplorer.setState({ projectId: "car", ready: true, tabs: [], activeId: null, openFile, selectCadReference });
});

it("opens the reference in its draft's worktree even when the explorer follows another root", () => {
  useExplorer.setState({ root: null });
  openComposerReference(scope, { file: "models/car.step", selector: "o1.3" });
  expect(openFile).toHaveBeenCalledWith("models/car.step", scope.root);
  expect(selectCadReference).toHaveBeenCalledWith("worktree-car", "o1.3");
});

it("does not resolve a bare selector against a same-named model in another workspace", () => {
  useExplorer.setState({ activeId: "main-car", tabs: [{ id: "main-car", kind: "file", path: "models/car.step", root: null }] as FileTab[] });
  expect(() => openComposerReference(scope, { file: "", selector: "o1.3" })).toThrow("this chat’s workspace");
  expect(openFile).not.toHaveBeenCalled();
  useExplorer.setState({ tabs: [{ id: "main-car", kind: "file", path: "models/car.step", root: scope.root }] as FileTab[] });
  openComposerReference(scope, { file: "", selector: "o1.3" });
  expect(openFile).toHaveBeenCalledWith("models/car.step", scope.root);
});

it("refuses a stale project's reference and opens whole-file chips without selecting geometry", () => {
  useExplorer.setState({ projectId: "other" });
  expect(() => openComposerReference(scope, { file: "models/car.step", selector: "o1" })).toThrow("project first");
  expect(openFile).not.toHaveBeenCalled();
  useExplorer.setState({ projectId: "car" });
  openComposerReference(scope, { file: "models/car.step", selector: "" });
  expect(selectCadReference).not.toHaveBeenCalled();
});
