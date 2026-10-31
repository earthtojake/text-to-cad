import { createContext, useContext, useEffect } from 'react';
/**
 * The document on screen, by its server's name and revision, and the file it shows (whose kind
 * says what it saves as). `planar`: an engine document the view holds drawn flat on z=0, which
 * holds no solid, so it writes a DXF too; a renderer that cannot tell leaves it out.
 */
export interface ExportView {
  doc: string; revision: string; file: string; name: string; planar?: boolean;
}
export const ExportContext = createContext<((source: ExportView | null) => void) | null>(null);
/** A renderer publishes only document state; its host owns saving files. */
export function useExportView(source: ExportView | null) {
  const publish = useContext(ExportContext);
  useEffect(() => { publish?.(source); return () => publish?.(null); }, [publish, source]);
}
