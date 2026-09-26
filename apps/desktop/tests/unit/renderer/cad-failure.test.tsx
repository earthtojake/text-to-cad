import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { DesktopCadFailure } from "@renderer/features/explorer/adapters/cadRuntime";

it("a runtime failure's log line truncates with a shared hint, never a native title", () => {
  const onReady = vi.fn();
  render(<DesktopCadFailure answer={{ reason: "runtime-not-ready", message: "cadgen: not found", log: "/Users/me/Library/Logs/Hardcore/cad-runtime.log" } as never}
    onReady={onReady} reload={() => {}} />);
  const log = screen.getByText(/^Log:/).closest("p")!;
  expect(log.hasAttribute("title")).toBe(false);
  expect(log.getAttribute("data-slot")).toBe("tooltip-trigger");
  expect(onReady).toHaveBeenCalledWith(false);
});
