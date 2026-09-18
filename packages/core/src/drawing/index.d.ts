export const MAX_DRAWING_BYTES: number;
export const MAX_DRAWING_ELEMENTS: number;
export interface DrawingBinaryFile { id: string; mimeType: string; dataURL: string; created: number }
export interface DrawingDocument {
  type: 'excalidraw'; version: 2; source: string;
  elements: Record<string, unknown>[];
  appState: Record<string, unknown>;
  files: Record<string, DrawingBinaryFile>;
}
export function emptyDrawingDocument(): DrawingDocument;
export function parseDrawingScene(serialized: string): DrawingDocument;
