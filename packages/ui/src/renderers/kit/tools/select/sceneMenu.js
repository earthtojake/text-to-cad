import { menuGroups, pickGroup, referenceGroup, zoomGroup } from "../../shell/viewMenu.js";

/**
 * What a 3D scene picks under a client point (`scene.pick(ray)`, as `usePointerPick.js` casts it),
 * through the camera of the viewport the shell hands a renderer's overlay; null for nothing.
 */
export function pickSceneAt(viewport, scene, clientX, clientY) {
  const runtime = viewport?.runtimeRef?.current;
  const rect = viewport?.hostRef?.current?.getBoundingClientRect?.();
  if (!runtime?.camera || !runtime.THREE || !rect?.width || !rect.height || typeof scene?.pick !== "function") return null;
  runtime.camera.updateMatrixWorld();
  const raycaster = new runtime.THREE.Raycaster();
  raycaster.setFromCamera(new runtime.THREE.Vector2(((clientX - rect.left) / rect.width) * 2 - 1, 1 - ((clientY - rect.top) / rect.height) * 2), runtime.camera);
  return scene.pick(raycaster.ray) || null;
}

/**
 * A 3D scene's menu, every view's groups (`kit/shell/viewMenu.js`): over something the scene picks,
 * its reference (with what is picked already), Select or Deselect, what the renderer adds (`more`,
 * a Hide), then the framing; over empty space, the framing alone. Zoom to selection frames
 * the scene's box of what is picked (`scene.selectionBounds`), and is off for a scene without one.
 *
 * @param {{ press: { clientX: number, clientY: number }, viewport: object | null, scene: object | null,
 *   selected: readonly string[], copyText(hit: object): string, onCopy(text: string): void,
 *   onSelect(hit: object, selected: boolean): void, viewer: () => object | null,
 *   more?: (hit: object) => object[], t: Function }} options  `selected`: what is picked, as the scene's
 *   picks name it; `viewer`: the shell's viewer (`resetZoom`, `zoomToBounds`).
 */
export function sceneMenuEntries({ press, viewport, scene, selected, copyText, onCopy, onSelect, viewer, more = null, t }) {
  const hit = pickSceneAt(viewport, scene, press.clientX, press.clientY);
  const zoom = zoomGroup({ t, onZoomFit: () => viewer()?.resetZoom?.(),
    onZoomSelection: scene?.selectionBounds ? () => { const box = scene.selectionBounds(selected); if (box) viewer()?.zoomToBounds?.(box); } : null,
    selectionAvailable: selected.length > 0 });
  if (!hit) return menuGroups(zoom);
  const isSelected = selected.includes(hit.id);
  const text = copyText(hit);
  return menuGroups(
    referenceGroup({ copyText: text, onCopy: () => onCopy(text), t }),
    pickGroup({ selected: isSelected, onSelect: () => onSelect(hit, isSelected), t }),
    more ? more(hit) : [],
    zoom);
}
