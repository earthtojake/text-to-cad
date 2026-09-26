import { expect, it } from "vitest";
import { terminalPromptRoot } from "@renderer/lib/terminal-workspace";
const project = { id: "project", path: "C:\\Projects\\Example" };
it("maps Windows checkout descendants to the checkout despite separator and case differences", () => {
  expect(terminalPromptRoot(project, "c:\\projects\\example\\src", [])).toBeNull();
  expect(terminalPromptRoot(project, "C:/Projects/Example/src/", [])).toBeNull();
  expect(terminalPromptRoot({ id: "drive", path: "C:\\" }, "c:/src", [])).toBeNull();
});
it("uses the recorded worktree root instead of a session's nested cwd", () => {
  const root = "C:\\Worktrees\\Feature";
  const sessions = [{ projectId: project.id, cwd: `${root}\\src`, worktreePath: root }];
  expect(terminalPromptRoot(project, "c:/worktrees/feature/src/tests", sessions)).toBe(root);
});
it("preserves UNC workspace identity while comparing paths case-insensitively", () => {
  const root = "\\\\Server\\Share\\Feature";
  expect(terminalPromptRoot(project, "//server/share/feature/src", [{ projectId: project.id, cwd: root, worktreePath: root }])).toBe(root);
});
it("does not infer ownership from another project or a sibling prefix", () => {
  const cwd = "C:\\Worktrees\\Feature-more\\src";
  expect(terminalPromptRoot(project, cwd, [{ projectId: project.id, cwd: "C:\\Worktrees\\Feature", worktreePath: "C:\\Worktrees\\Feature" }])).toBe(cwd);
  expect(terminalPromptRoot(project, cwd, [{ projectId: "other", cwd, worktreePath: "C:\\Worktrees" }])).toBe(cwd);
});
it("preserves POSIX case sensitivity and attributes checkout subdirectories to their checkout", () => {
  const project = { id: "posix", path: "/projects/Example" };
  expect(terminalPromptRoot(project, "/projects/Example/src", [])).toBeNull();
  expect(terminalPromptRoot(project, "/projects/example/src", [])).toBe("/projects/example/src");
});
