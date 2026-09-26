/** Step 3b: the viewer component — any React component; `data` is what `prepare` read. */
import { useEffect, useMemo } from "react";

import type { FileRendererProps } from "@hardcore/ui/file-viewer";

import { parseTable, separatorFor } from "./table";

export default function CsvTable({ data, file, onReady }: FileRendererProps<{ text: string }>) {
  const [header = [], ...rows] = useMemo(() => parseTable(data.text, separatorFor(file.path)), [data.text, file.path]);
  useEffect(() => onReady(true), [onReady]);
  return (
    <div className="h-full overflow-auto p-3">
      <table className="w-full border-collapse text-xs" data-csv-table="">
        <thead className="sticky top-0 bg-background">
          <tr>{header.map((cell, i) => <th className="border-b px-2 py-1.5 text-left font-medium" key={i}>{cell}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr className="odd:bg-muted/30" key={r}>{row.map((cell, c) => <td className="px-2 py-1 tabular-nums" key={c}>{cell}</td>)}</tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted-foreground">{rows.length} rows × {header.length} columns</p>
    </div>
  );
}
