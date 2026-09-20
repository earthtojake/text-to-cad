import { convertToExcalidrawElements, exportToCanvas, getCommonBounds } from '@excalidraw/excalidraw';
import type { AppState, BinaryFiles } from '@excalidraw/excalidraw/types';
import type { ExcalidrawElement } from '@excalidraw/excalidraw/element/types';
import { FILL_ANALYSIS_MAX_DIMENSION, FILL_CONNECT_GAP_PX, findFillRegion, pairNearbyBoundaryEndpoints } from '@hardcore/core/lib/drawing/fillRegion.js';

/**
 * The Fill tool, which the SDK does not have: click inside drawn ink and the
 * area becomes a translucent polygon of the current color. The fill is an
 * ordinary element afterwards, so it moves, erases and undoes like any ink.
 * The outline need not be closed (`fillRegion.js` joins and guesses).
 */

/** Translucent, so a fill marks an area without hiding the model or drawing under it. */
export const FILL_OPACITY = 35;
const PADDING = 12;

// A fill is recognized by what it is, not by custom data: a retained scene keeps
// only portable fields, and an earlier fill must never become an outline.
export const isFillElement = (element: ExcalidrawElement) =>
  element.type === 'line' && element.strokeColor === 'transparent' && element.backgroundColor !== 'transparent';

type Point = { x: number; y: number };
const rotated = (element: ExcalidrawElement, [x, y]: readonly [number, number]): Point => {
  const cx = element.x + element.width / 2, cy = element.y + element.height / 2;
  const dx = element.x + x - cx, dy = element.y + y - cy, cos = Math.cos(element.angle), sin = Math.sin(element.angle);
  return { x: cx + dx * cos - dy * sin, y: cy + dx * sin + dy * cos };
};

/** The ends of every open stroke: where an outline that was not closed has its gap. */
function openEnds(elements: readonly ExcalidrawElement[]) {
  return elements.flatMap(element => {
    if (element.type !== 'freedraw' && element.type !== 'line' && element.type !== 'arrow') return [];
    const points = element.points;
    if (points.length < 2) return [];
    return [points[0], points[points.length - 1]].map(point => ({ point: rotated(element, point as [number, number]), strokeId: element.id, allowSelfConnect: true }));
  });
}

function stroke(mask: Uint8Array, width: number, height: number, from: [number, number], to: [number, number]) {
  const steps = Math.max(Math.abs(to[0] - from[0]), Math.abs(to[1] - from[1]), 1);
  for (let step = 0; step <= steps; step += 1) {
    const x = Math.round(from[0] + (to[0] - from[0]) * step / steps), y = Math.round(from[1] + (to[1] - from[1]) * step / steps);
    for (let dy = -1; dy <= 1; dy += 1) for (let dx = -1; dx <= 1; dx += 1) {
      if (x + dx >= 0 && y + dy >= 0 && x + dx < width && y + dy < height) mask[(y + dy) * width + x + dx] = 1;
    }
  }
}

/** The element that fills the area around `seed` (scene coordinates), or `null` when no ink indicates one. */
export async function fillElementAt(seed: Point, scene: { elements: readonly ExcalidrawElement[]; appState: AppState; files: BinaryFiles }, color: string) {
  const outlines = scene.elements.filter(element => !element.isDeleted && !isFillElement(element));
  if (!outlines.length) return null;
  const [minX, minY, maxX, maxY] = getCommonBounds(outlines);
  if (seed.x < minX || seed.x > maxX || seed.y < minY || seed.y > maxY) return null;
  const scale = Math.min(2, FILL_ANALYSIS_MAX_DIMENSION / Math.max(maxX - minX + PADDING * 2, maxY - minY + PADDING * 2, 1));
  // The ink as the SDK draws it, whatever the element type, without the fills.
  const canvas = await exportToCanvas({ elements: outlines, files: scene.files, exportPadding: PADDING,
    appState: { ...scene.appState, exportBackground: false, exportWithDarkMode: false },
    getDimensions: (width: number, height: number) => ({ width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)), scale }) });
  const { width, height } = canvas;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context || width < 3 || height < 3) return null;
  const { data } = context.getImageData(0, 0, width, height);
  const ink = new Uint8Array(width * height);
  for (let index = 0; index < ink.length; index += 1) ink[index] = data[index * 4 + 3] > 20 ? 1 : 0;
  const toMask = (point: Point): [number, number] => [(point.x - minX + PADDING) * scale, (point.y - minY + PADDING) * scale];
  const ends = openEnds(outlines).map(end => ({ ...end, point: toMask(end.point) }));
  const zoom = scene.appState.zoom?.value || 1;
  const region = findFillRegion((gapPx: number) => {
    const mask = ink.slice();
    for (const [from, to] of pairNearbyBoundaryEndpoints(ends, gapPx) as [[number, number], [number, number]][]) stroke(mask, width, height, from, to);
    return mask;
  }, width, height, toMask(seed), { gapPx: FILL_CONNECT_GAP_PX / zoom * scale });
  if (!region) return null;
  const outline = region.points.map(point => ({ x: minX - PADDING + point.x * width / scale, y: minY - PADDING + point.y * height / scale }));
  const [first] = outline;
  const points = [...outline, first].map(point => [point.x - first.x, point.y - first.y] as [number, number]);
  const [element] = convertToExcalidrawElements([{ type: 'line', x: first.x, y: first.y, points, strokeColor: 'transparent',
    backgroundColor: color, fillStyle: 'solid', opacity: FILL_OPACITY, roughness: 0, strokeWidth: 1 }] as Parameters<typeof convertToExcalidrawElements>[0]);
  return element ?? null;
}
