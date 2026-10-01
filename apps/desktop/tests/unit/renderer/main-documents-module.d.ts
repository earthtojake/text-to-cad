// The one value the renderer's tests read from main's plain-JS tool table (the web tsconfig does not compile .mjs).
declare module '@main/integrations/documents/module.mjs' {
  export const MAX_DOCUMENT_CHARS: number;
}
