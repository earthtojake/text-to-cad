// Preview's bar and playbar hide two seconds after the pointer last rests over the view (counted from
// the frame that shows them), and a person's pointer, moving to one of their controls, brings them
// back and holds them while it rests there. A spec presses one the same way: its pointer moves over
// the view until the bar says it is visible (`data-state`), moves onto the control (which holds the
// bar), and presses it. Playwright checks what is under a point before it moves there, so a press
// alone on a hidden bar would never bring it back.

/** Press `control`, a control of Preview's bar or playbar, in `pane` (the harness's view, `[data-testid=…]`). */
export async function pressInPreview(page, pane, control) {
  const view = await pane.locator('[data-preview-view]').boundingBox();
  const visible = () => pane.locator('[data-preview-bar][data-state="visible"]').waitFor({ state: 'attached' });
  await page.mouse.move(view.x + view.width / 2, view.y + view.height / 2);
  await visible();
  const box = await control.boundingBox();
  const [x, y] = [box.x + box.width / 2, box.y + box.height / 2];
  await page.mouse.move(x, y);
  await visible();
  await page.mouse.move(x + 1, y);  // over the bar while it shows: resting there holds it
  await visible();
  await control.click();
}
