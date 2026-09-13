export interface CsvParseResult {
  rows: string[][];
  truncatedRows: number;
  truncatedColumns: number;
}

export const MAX_PREVIEW_ROWS = 1000;
export const MAX_PREVIEW_COLUMNS = 100;

export function parseCsv(content: string): CsvParseResult {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let inQuotes = false;
  let truncatedColumns = 0;
  let truncatedRows = 0;

  const pushCell = () => {
    if (row.length < MAX_PREVIEW_COLUMNS) {
      row.push(cell);
    } else {
      truncatedColumns += 1;
    }
    cell = '';
  };
  const pushRow = () => {
    pushCell();
    if (rows.length < MAX_PREVIEW_ROWS) {
      rows.push(row);
    } else {
      truncatedRows += 1;
    }
    row = [];
  };

  for (let index = 0; index < content.length; index += 1) {
    const char = content[index];
    if (char === '"') {
      if (inQuotes && content[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      pushCell();
    } else if ((char === '\n' || char === '\r') && !inQuotes) {
      if (char === '\r' && content[index + 1] === '\n') index += 1;
      pushRow();
    } else {
      cell += char;
    }
  }

  if (cell.length > 0 || row.length > 0 || content.endsWith(',')) {
    pushRow();
  }

  return { rows, truncatedRows, truncatedColumns };
}
