/**
 * The corner macOS draws over.
 *
 * With `titleBarStyle: "hiddenInset"` the close, minimise and zoom buttons are
 * painted by AppKit on top of whatever the renderer puts in the top-left of the
 * window. Nothing the app draws there is visible, and nothing there can be
 * clicked — a button under the lights is a button nobody can press, and the
 * defect looks like a rendering glitch rather than a layout one.
 *
 * So every state that can put something in that corner is checked here: the
 * sidebar leftmost, the sidebar hidden and the session's bar leftmost, the
 * sidebar at its narrowest, the window at its minimum size, the explorer open,
 * Settings (which replaces the shell), and the command palette over all of it.
 *
 * The rectangle is not a number typed into this file. Main pins the cluster's
 * origin (`trafficLightPosition`) and Chromium reports where content may start
 * past it (the window-controls overlay, read by the renderer into
 * `--titlebar-inset`); the assertions use that reading, and one test fails if
 * it and the constant in `src/shared/titlebar.ts` ever drift apart — which is
 * how a macOS that draws the buttons differently announces itself.
 *
 * Windows and Linux keep their native frame and reserve nothing; there the
 * inset is 0 and the geometry assertions are trivially true, so the suite
 * asserts that instead.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  _electron as electron,
  expect,
  test,
  type ElectronApplication,
  type Locator,
  type Page,
} from "@playwright/test";

import { TITLEBAR_HEIGHT, TRAFFIC_LIGHTS_INSET, trafficLightPosition } from "../../src/shared/titlebar";

/**
 * `page.evaluate` bodies run in the renderer; see the note in shell.spec.ts.
 * This file is compiled with the node tsconfig, which has no DOM library, so
 * the handful of DOM shapes these snippets touch are declared here — as
 * module-scoped declarations, which is what keeps `document` out of the main
 * process's types.
 */
declare const window: {
  hardcore: {
    projects: {
      addPath(request: { path: string }): Promise<{ id: string }>;
      remove(request: { id: string }): Promise<void>;
    };
  };
};
interface DomRect {
  left: number;
  top: number;
  right: number;
  width: number;
  height: number;
}
interface DomNode {
  id: string;
  parentElement: DomNode | null;
  nodeName: string;
  textContent: string | null;
  style: { cssText: string };
  getAttribute(name: string): string | null;
  getBoundingClientRect(): DomRect;
  querySelectorAll(selector: string): DomNode[];
  appendChild(child: DomNode): void;
  remove(): void;
}
declare const document: {
  body: DomNode;
  createElement(tag: string): DomNode;
  getElementById(id: string): DomNode | null;
  querySelector(selector: string): DomNode | null;
  querySelectorAll(selector: string): DomNode[];
};
declare function getComputedStyle(node: DomNode): { getPropertyValue(name: string): string };

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const screenshots = path.join(appRoot, "tests", "e2e", "__screenshots__");
const isMac = process.platform === "darwin";

let app: ElectronApplication;
let page: Page;
let userData: string;
/** The room the window's own controls need, as the running app measured it. */
let inset: number;

test.beforeAll(async () => {
  userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-titlebar-e2e-"));
  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, NODE_ENV: "test" },
  });
  page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  inset = await readInset();
});

test.afterAll(async () => {
  await app?.close();
  fs.rmSync(userData, { recursive: true, force: true });
});

/**
 * The pin and the reservation, from the two processes that own them.
 *
 * Main's answer is where the cluster starts; the renderer's is where content
 * may start. The constant sits between them: it is what the CSS reserves
 * before the first measurement lands, so a macOS that reports something else
 * has to be met by changing both `src/shared/titlebar.ts` and `globals.css`,
 * and this is where that is noticed.
 */
test("the lights are pinned where the layout expects them", async () => {
  const position = await app.evaluate(({ BrowserWindow }) => {
    const win = BrowserWindow.getAllWindows()[0]!;
    return win.getWindowButtonPosition();
  });

  if (!isMac) {
    expect(position).toBeNull();
    expect(inset).toBe(0);
    return;
  }

  expect(position).toEqual(trafficLightPosition());
  // Centred in the strip: as much room below the cluster as above it.
  expect(position!.y * 2).toBeLessThanOrEqual(TITLEBAR_HEIGHT);
  expect(
    inset,
    "macOS reserves a different width for the traffic lights than TRAFFIC_LIGHTS_INSET; " +
      "update src/shared/titlebar.ts and the .platform-mac fallback in globals.css together",
  ).toBe(TRAFFIC_LIGHTS_INSET);
  // And the cluster starts inside what is reserved for it.
  expect(position!.x).toBeLessThan(inset);
});

test("the sidebar's strip is clear, open and at its narrowest", async () => {
  await expectLeftmost("sidebar", "[data-sidebar-titlebar]");
  await shootTitlebar("titlebar-sidebar.png");

  // Dragged as far left as it goes. The sidebar's minimum (180px) is wider
  // than the lights need, so the strip cannot be squeezed under them — but
  // the drag is what would prove otherwise, and a panel that collapses under
  // the pressure hands the corner to the session's bar, which is checked too.
  const sidebar = page.locator("[data-panel]").first();
  const separator = page.locator("[data-separator]").first();
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await dragSeparator(separator, -4000);
  }
  const width = (await sidebar.boundingBox())?.width ?? 0;
  if (width > 0) {
    expect(width, "the sidebar was dragged under its minimum").toBeGreaterThanOrEqual(179);
    await expectLeftmost("sidebar", "[data-sidebar-titlebar]");
  } else {
    await expectLeftmost("session", "[data-session-header]");
  }

  // Back to a width the tests below can click in.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await dragSeparator(separator, 4000);
  }
  await expectLeftmost("sidebar", "[data-sidebar-titlebar]");
});

test("the session's bar takes the corner when the sidebar is hidden", async () => {
  await collapseSidebar(true);
  await expectLeftmost("session", "[data-session-header]");
  await shootTitlebar("titlebar-session.png");

  // At the window's minimum size, where the panes have the least room to
  // give: the inset is a fixed number of pixels, not a share of the width.
  await setContentSize(900, 600);
  await expectLeftmost("session", "[data-session-header]");
  await collapseSidebar(false);
  await expectLeftmost("sidebar", "[data-sidebar-titlebar]");
  await setContentSize(1440, 900);
});

test("a project and its explorer do not move the corner", async () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-titlebar-project-"));
  const project = await page.evaluate(
    (directory) => window.hardcore.projects.addPath({ path: directory }),
    fixture,
  );
  await expect(page.getByRole("button", { name: "Toggle explorer" })).toBeVisible();
  await page.getByRole("button", { name: "Toggle explorer" }).click();
  await expect
    .poll(async () => (await page.getByTestId("explorer").boundingBox())?.width ?? 0)
    .toBeGreaterThan(0);

  // Three panes, and then three panes with the sidebar gone: the explorer's
  // strip is never at the window's left edge, because the session never
  // collapses, but that is a claim worth failing on.
  await expectLeftmost("sidebar", "[data-sidebar-titlebar]");
  await collapseSidebar(true);
  await expectLeftmost("session", "[data-session-header]");
  await collapseSidebar(false);

  await page.evaluate((id) => window.hardcore.projects.remove({ id }), project.id);
  await expect(page.getByText("Add a project to get started")).toBeVisible();
  fs.rmSync(fixture, { recursive: true, force: true });
});

test("Settings reserves the corner itself", async () => {
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "General" })).toBeVisible();

  await expectClear("settings");
  await expectFirstControlClears("[data-settings-header]");
  await expectDragRegion("[data-settings-header]");
  await shootTitlebar("titlebar-settings.png");

  await page.getByRole("button", { name: "Back to app" }).click();
  await expect(page.getByText("Add a project to get started")).toBeVisible();
});

test("the command palette puts nothing in the corner", async () => {
  await page.keyboard.press(process.platform === "darwin" ? "Meta+K" : "Control+K");
  await expect(page.getByPlaceholder("Search projects and commands…")).toBeVisible();
  await expectClear("palette");
  await page.keyboard.press("Escape");
  await expect(page.getByPlaceholder("Search projects and commands…")).toBeHidden();
});

/* -------------------------------------------------------------------------- */

/** What the renderer reserved, in CSS pixels. */
async function readInset(): Promise<number> {
  return page.evaluate(() => {
    const probe = document.createElement("div");
    probe.style.cssText =
      "position:fixed;left:0;top:0;height:1px;width:var(--titlebar-inset);visibility:hidden";
    document.body.appendChild(probe);
    const width = probe.getBoundingClientRect().width;
    probe.remove();
    return Math.round(width);
  });
}

/**
 * The whole check for one leftmost bar: nothing interactive under the lights,
 * the bar's own first control past them, and the strip draggable with its
 * controls opted out of the drag.
 */
async function expectLeftmost(leftmost: "sidebar" | "session", bar: string) {
  await expect(page.locator("[data-shell]")).toHaveAttribute("data-leftmost", leftmost);
  await expectClear(leftmost);
  await expectFirstControlClears(bar);
  await expectDragRegion(bar);
}

/**
 * No interactive element anywhere on the page overlaps the reserved corner.
 *
 * Deliberately the whole document rather than the bar being tested: a dialog,
 * a toast or a menu that opens over the top-left corner is the same defect,
 * and only a page-wide sweep catches one.
 */
async function expectClear(label: string) {
  const trespassers = await page.evaluate(
    ([reserved, height]) => {
      const found: { label: string; x: number; y: number }[] = [];
      const selector =
        "button, [role=button], a[href], input, select, textarea, [contenteditable=true], " +
        "[role=tab], [role=option], [role=menuitem], [data-separator]";
      for (const node of Array.from(document.querySelectorAll(selector))) {
        const rect = node.getBoundingClientRect();
        // A pane collapsed to nothing takes its buttons off the left of the
        // window with it; they are clipped, unclickable and not in the corner.
        if (rect.width === 0 || rect.height === 0 || rect.right <= 0) {
          continue;
        }
        // In the strip, not merely passing through it: a pane divider runs the
        // whole height of the window and is grabbed anywhere along it, so the
        // 36 pixels the lights cover are not its only handle. What counts is a
        // control that lives in this row.
        if (rect.top + rect.height / 2 > height) {
          continue;
        }
        if (rect.left < reserved) {
          found.push({
            label: (node.getAttribute("aria-label") ?? node.textContent ?? node.nodeName)
              .trim()
              .slice(0, 40),
            x: Math.round(rect.left),
            y: Math.round(rect.top),
          });
        }
      }
      return found;
    },
    [inset, TITLEBAR_HEIGHT] as const,
  );
  expect(trespassers, `${label}: these controls are under the traffic lights`).toEqual([]);
}

/** The leftmost bar's own first control starts past the lights. */
async function expectFirstControlClears(bar: string) {
  const first = await page.evaluate((selector) => {
    const strip = document.querySelector(selector);
    if (!strip) {
      return null;
    }
    for (const node of Array.from(strip.querySelectorAll("button, [role=button], input"))) {
      const rect = node.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        return { x: Math.round(rect.left), label: node.textContent?.trim().slice(0, 40) ?? "" };
      }
    }
    return null;
  }, bar);
  expect(first, `${bar} has no control to check`).not.toBeNull();
  expect(first!.x, `${bar}'s first control starts inside the lights' room`).toBeGreaterThanOrEqual(
    inset,
  );
}

/**
 * The strip is the window's drag handle and its controls are not: a title bar
 * that cannot be dragged, or a button that drags the window instead of firing,
 * are both this one property being wrong.
 */
async function expectDragRegion(bar: string) {
  const regions = await page.evaluate((selector) => {
    const strip = document.querySelector(selector);
    if (!strip) {
      return null;
    }
    const region = (node: DomNode) =>
      getComputedStyle(node).getPropertyValue("-webkit-app-region").trim();
    // Chromium subtracts a `no-drag` element's whole box from the region, so
    // the opt-out is allowed to be a wrapper around the buttons rather than
    // the buttons themselves — what matters is that one is met on the way up
    // from each control to the strip.
    const optedOut = (node: DomNode) => {
      for (let current: DomNode | null = node; current; current = current.parentElement) {
        const value = region(current);
        if (value === "no-drag") {
          return true;
        }
        if (current === strip) {
          return false;
        }
      }
      return false;
    };
    return {
      strip: region(strip),
      dragging: Array.from(strip.querySelectorAll("button"))
        .filter((node) => !optedOut(node))
        .map((node) => (node.getAttribute("aria-label") ?? node.textContent ?? "").trim()),
    };
  }, bar);
  expect(regions, `${bar} is not in the document`).not.toBeNull();
  expect(regions!.strip, `${bar} is not a drag region`).toBe("drag");
  expect(regions!.dragging, `these controls in ${bar} drag the window instead`).toEqual([]);
}

async function collapseSidebar(collapsed: boolean) {
  const sidebar = page.locator("[data-panel]").first();
  const width = (await sidebar.boundingBox())?.width ?? 0;
  if (collapsed === (width === 0)) {
    return;
  }
  const toggle = collapsed
    ? sidebar.getByRole("button", { name: "Toggle sidebar" })
    : page.locator("[data-session-header]").getByRole("button", { name: "Toggle sidebar" });
  await toggle.click();
  await expect
    .poll(async () => ((await sidebar.boundingBox())?.width ?? 0) === 0)
    .toBe(collapsed);
}

async function setContentSize(width: number, height: number) {
  await app.evaluate(({ BrowserWindow }, size) => {
    BrowserWindow.getAllWindows()[0]!.setContentSize(size.width, size.height);
  }, { width, height });
  // The layout is reapplied on the frame after the group's resize observation.
  await page.waitForTimeout(300);
}

/** Drag the group's separator `by` pixels; the library clamps it. */
async function dragSeparator(separator: Locator, by: number) {
  const box = await separator.boundingBox();
  if (!box) {
    return;
  }
  const y = box.y + box.height / 2;
  await page.mouse.move(box.x + box.width / 2, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + by, y, { steps: 12 });
  await page.mouse.up();
  await page.waitForTimeout(200);
}

/**
 * The corner, photographed with the reserved room drawn on it.
 *
 * The traffic lights are AppKit's and never appear in a screenshot of the web
 * contents, so a picture of this corner is a picture of an empty gap. The
 * marker is what makes it reviewable: the box is the room the lights are in,
 * and everything the app drew should be outside it.
 */
async function shootTitlebar(name: string) {
  await page.evaluate(
    ([reserved, height]) => {
      const marker = document.createElement("div");
      marker.id = "titlebar-marker";
      marker.style.cssText =
        `position:fixed;left:0;top:0;width:${reserved}px;height:${height}px;` +
        "background:rgba(255,64,64,0.28);outline:1px solid rgba(255,64,64,0.9);" +
        "pointer-events:none;z-index:2147483647";
      document.body.appendChild(marker);
    },
    [inset, TITLEBAR_HEIGHT] as const,
  );
  await page.screenshot({
    path: path.join(screenshots, name),
    animations: "disabled",
    clip: { x: 0, y: 0, width: 720, height: 96 },
  });
  await page.evaluate(() => document.getElementById("titlebar-marker")?.remove());
}
