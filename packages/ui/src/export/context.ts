import { createContext, useContext, useEffect } from 'react';
export interface ExportView {
  doc: string; revision: string; file: string; name: string; preview: boolean;
}
export const ExportContext = createContext<((source: ExportView | null) => void) | null>(null);
/** A renderer publishes only document state; its host owns saving files. */
export function useExportView(source: ExportView | null) {
  const publish = useContext(ExportContext);
  useEffect(() => { publish?.(source); return () => publish?.(null); }, [publish, source]);
}
