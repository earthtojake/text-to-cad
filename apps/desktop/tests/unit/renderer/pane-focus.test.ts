import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { focusSessionHome } from "@renderer/app/pane-focus";

/**
 * The composer's editor mounts a frame after its pane (`immediatelyRender: false`). Leaving
 * Settings must wait that frame for it rather than focus a header button on the way, which a
 * screen reader announces.
 */
let frames: FrameRequestCallback[] = [];

beforeEach(() => {
  frames = [];
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => frames.push(callback));
  document.body.innerHTML = '<div id="session"><button id="toggle" type="button">Toggle sidebar</button></div>';
});
afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

const flushFrame = () => frames.splice(0).forEach((callback) => callback(0));

it("lands on a composer that appears one frame late, and never on the header button", () => {
  const toggle = document.getElementById("toggle")!;
  const focused = vi.fn();
  toggle.addEventListener("focus", focused);

  focusSessionHome();
  expect(toggle).not.toHaveFocus();

  const composer = document.createElement("div");
  composer.setAttribute("data-composer-input", "");
  composer.setAttribute("contenteditable", "true");
  document.getElementById("session")!.append(composer);
  flushFrame();

  expect(composer).toHaveFocus();
  expect(focused).not.toHaveBeenCalled();
});

it("falls back to the pane's first control when there is no composer after the frame", () => {
  focusSessionHome();
  flushFrame();
  expect(document.getElementById("toggle")).toHaveFocus();
});
