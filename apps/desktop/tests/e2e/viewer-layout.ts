import { expect, type Page } from "@playwright/test";

/**
 * The file viewer lays itself out for a phone below 720px of its OWN width
 * (`VIEWER_MOBILE_BREAKPOINT`, `packages/ui/src/file-viewer/responsive.js`): floating sheets
 * that nothing opens but a press, one crumb, no view cube. The explorer pane opens at 560px
 * (`PANE_LIMITS.explorer.default`), so a spec about the wide layout — a panel column beside
 * the model, the tree kept up across picks, a file's Settings open by default — gives the
 * explorer that room first, by its separator, the way a person would.
 */
export const VIEWER_DESKTOP_MIN = 740;

export async function widenExplorer(page: Page, width = VIEWER_DESKTOP_MIN) {
  const explorer = page.getByTestId("explorer");
  await expect(explorer).toBeVisible();
  const current = (await explorer.boundingBox())!.width;
  if (current >= width) return;
  const box = (await page.locator("[data-separator=explorer]").boundingBox())!;
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x - (width - current) - 8, y, { steps: 12 });
  await page.mouse.up();
  await expect.poll(async () => (await explorer.boundingBox())?.width ?? 0).toBeGreaterThanOrEqual(width);
}
