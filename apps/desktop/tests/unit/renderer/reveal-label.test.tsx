/**
 * "Reveal in Finder" is the Mac's word: the session header's menu and a project's menu name the
 * platform's own file browser, as the explorer's entry menu does.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";

import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@renderer/components/ui/dropdown-menu";
import { ProjectMenuItems } from "@renderer/features/sidebar/project-menu";
import { SessionHeader } from "@renderer/features/session/SessionHeader";
import type { Project, Session } from "@shared/types";

const where = vi.hoisted(() => ({ platform: "win32" as "darwin" | "win32" | "linux" }));
vi.mock("@renderer/lib/platform", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  get platform() {
    return where.platform;
  },
}));

const SESSION = { id: "s1", projectId: "p", agentId: "codex", cwd: "/p", title: "Bracket", status: "idle", archived: false } as unknown as Session;
const PROJECT = { id: "p", path: "/p", name: "p" } as unknown as Project;

beforeEach(() => {
  where.platform = "win32";
});

describe.each([
  ["win32", "Show in Explorer"],
  ["linux", "Show in file manager"],
  ["darwin", "Reveal in Finder"],
] as const)("on %s", (name, label) => {
  it("the session header's menu says " + label, async () => {
    where.platform = name;
    render(
      <TooltipProvider>
        <SessionHeader session={SESSION} title="Bracket" />
      </TooltipProvider>,
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "Session actions" }));
    expect(screen.getByRole("menuitem", { name: label })).toBeInTheDocument();
  });

  it("a project's menu says " + label, () => {
    where.platform = name;
    render(
      <DropdownMenu open>
        <DropdownMenuTrigger>menu</DropdownMenuTrigger>
        <DropdownMenuContent>
          <ProjectMenuItems project={PROJECT} />
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    expect(screen.getByRole("menuitem", { name: label })).toBeInTheDocument();
  });
});
