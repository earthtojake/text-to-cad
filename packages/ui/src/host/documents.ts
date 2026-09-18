import type { DocumentSaveResult, TextDocument } from '../file-viewer/types.js';
/** Host-owned drafts outlive mounted editors; bytes never enter persisted view state. */
export interface TextDraft { base: TextDocument; value: string; stale: boolean }
export interface DocumentDrafts {
  get(sourceId: string, path: string): TextDraft | undefined;
  put(sourceId: string, path: string, draft: TextDraft | null): void;
}
export interface LiveTextSnapshot {
  content: string; revision: string; diskRevision?: string; dirty: boolean;
  readOnly: boolean; stale: boolean;
}
export interface LiveTextDocument {
  sourceId: string; path: string;
  read(): LiveTextSnapshot;
  replace(content: string, expectedRevision: string): LiveTextSnapshot;
  save(expectedRevision: string): Promise<DocumentSaveResult>;
}
export interface LivePdfSnapshot {
  sourceId: string; path: string; revision?: string;
  page: number; pageCount: number; selection: string;
}
export interface LivePdfDocument {
  sourceId: string; path: string;
  state(): LivePdfSnapshot;
  read(startPage?: number, endPage?: number): Promise<{ page: number; text: string }[]>;
  setPage(page: number): LivePdfSnapshot;
  capture(page?: number): Promise<Blob>;
}
