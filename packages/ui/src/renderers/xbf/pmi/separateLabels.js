// Callouts that would cover one another on screen, set apart: each label the code never placed
// (`movable`) that overlaps a label before it steps down below that one, a few pixels clear, until it
// overlaps none; a label the code placed stays where it was placed, and the others keep clear of it.
// In screen pixels, every frame the camera moves: what it reads as, never where it is in the model.

const GAP_PX = 3;
const overlaps = (a, b) => Math.abs(a.x - b.x) * 2 < a.w + b.w && Math.abs(a.y - b.y) * 2 < a.h + b.h;

/**
 * @param {Array<{ x: number, y: number, w: number, h: number, movable: boolean }>} boxes  Centred boxes, in drawing order.
 * @returns {Array<{ x: number, y: number }>} Where each is drawn.
 */
export function separateLabels(boxes) {
  const placed = [];
  // The fixed ones first: the movable keep clear of every one of them, whatever the order.
  const fixed = boxes.filter(box => !box.movable);
  return boxes.map((box) => {
    if (!box.movable) { placed.push(box); return { x: box.x, y: box.y }; }
    const at = { ...box };
    for (let tries = 0; tries <= boxes.length; tries += 1) {
      const hit = [...fixed, ...placed].find(other => other !== box && overlaps(at, other));
      if (!hit) break;
      at.y = hit.y + (hit.h + at.h) / 2 + GAP_PX;
    }
    placed.push(at);
    return { x: at.x, y: at.y };
  });
}
