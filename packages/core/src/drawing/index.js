/** Bounded in-memory Excalidraw scenes. No editor or storage is loaded here. */
export const MAX_DRAWING_BYTES = 20 * 1024 * 1024;
export const MAX_DRAWING_ELEMENTS = 10_000;
const elementTypes = new Set(['rectangle', 'diamond', 'ellipse', 'line', 'arrow', 'freedraw', 'text', 'image', 'frame']);
const appStateKeys = ['viewBackgroundColor', 'gridSize', 'gridStep', 'gridModeEnabled', 'scrollX', 'scrollY',
  'currentItemStrokeColor', 'currentItemBackgroundColor', 'currentItemFillStyle', 'currentItemStrokeWidth',
  'currentItemStrokeStyle', 'currentItemRoughness', 'currentItemOpacity', 'currentItemFontFamily',
  'currentItemFontSize', 'currentItemTextAlign', 'currentItemStartArrowhead', 'currentItemEndArrowhead'];
const record = value => !!value && typeof value === 'object' && !Array.isArray(value);

export function emptyDrawingDocument() {
  return { type: 'excalidraw', version: 2, source: 'Hardcore', elements: [], appState: { viewBackgroundColor: '#ffffff' }, files: {} };
}

/** Bound and validate untrusted JSON before the editor's own version restoration. */
export function parseDrawingScene(serialized) {
  if (typeof serialized !== 'string' || serialized.length > MAX_DRAWING_BYTES
    || new TextEncoder().encode(serialized).byteLength > MAX_DRAWING_BYTES) {
    throw new Error('Drawing documents must be at most 20 MiB.');
  }
  let input;
  try { input = JSON.parse(serialized); } catch { throw new Error('This is not a valid Excalidraw JSON document.'); }
  if (!record(input) || input.type !== 'excalidraw' || input.version !== 2 || !Array.isArray(input.elements)
    || input.elements.length > MAX_DRAWING_ELEMENTS) {
    throw new Error('Expected an Excalidraw v2 document with at most 10,000 elements.');
  }
  const ids = new Set();
  const elements = input.elements.map(element => {
    if (!record(element) || !elementTypes.has(element.type) || typeof element.id !== 'string'
      || !element.id || ids.has(element.id)) throw new Error('The drawing contains an invalid or unsupported element.');
    ids.add(element.id);
    for (const key of ['x', 'y', 'width', 'height']) {
      if (!Number.isFinite(element[key]) || Math.abs(element[key]) > 10_000_000) {
        throw new Error('The drawing contains invalid element coordinates.');
      }
    }
    if (element.type === 'text' && typeof element.text !== 'string') throw new Error('The drawing contains invalid text.');
    if (['line', 'arrow', 'freedraw'].includes(element.type) && (!Array.isArray(element.points)
      || element.points.some(point => !Array.isArray(point) || point.length !== 2
        || point.some(value => !Number.isFinite(value) || Math.abs(value) > 10_000_000)))) {
      throw new Error('The drawing contains invalid line points.');
    }
    // Drawings are visual context, never embedded pages or navigation. The SDK
    // restores supported element fields; links/custom application data are discarded.
    const { customData: _customData, ...copy } = element;
    return { ...copy, link: null };
  });
  if (input.files != null && !record(input.files)) throw new Error('The drawing contains invalid images.');
  const files = {};
  for (const [id, file] of Object.entries(input.files ?? {})) {
    if (['__proto__', 'constructor', 'prototype'].includes(id) || !record(file) || file.id !== id
      || !['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(file.mimeType)
      || typeof file.dataURL !== 'string' || !file.dataURL.startsWith(`data:${file.mimeType};base64,`)
      || !/^[A-Za-z0-9+/]*={0,2}$/.test(file.dataURL.slice(file.dataURL.indexOf(',') + 1))) {
      throw new Error('Drawings support embedded PNG, JPEG, GIF and WebP images only.');
    }
    files[id] = { id, mimeType: file.mimeType, dataURL: file.dataURL,
      created: Number.isFinite(file.created) ? file.created : 0 };
  }
  const appState = { viewBackgroundColor: '#ffffff' };
  if (record(input.appState)) {
    for (const key of appStateKeys) {
      const value = input.appState[key];
      if (typeof value === 'string' || typeof value === 'boolean' || value === null
        || (typeof value === 'number' && Number.isFinite(value))) appState[key] = value;
    }
    const zoom = input.appState.zoom?.value;
    if (Number.isFinite(zoom) && zoom >= 0.1 && zoom <= 30) appState.zoom = { value: zoom };
  }
  return { type: 'excalidraw', version: 2, source: 'Hardcore', elements, appState, files };
}
