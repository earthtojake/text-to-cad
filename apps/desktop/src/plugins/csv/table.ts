/** Rows of a CSV (or, for `.tsv`, tab-separated) text. Quoted fields may hold the separator, "" and newlines. */
export function parseTable(text: string, separator = ","): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (char === '"') quoted = false;
      else field += char;
    } else if (char === '"') quoted = true;
    else if (char === separator) { row.push(field); field = ""; }
    else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else field += char;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  return rows;
}

/** What the agent reads with `csv_state`. */
export function tableState(path: string, rows: string[][]) {
  const [header = [], ...body] = rows;
  return { path, header, rows: body.length, columns: header.length, firstRows: body.slice(0, 5) };
}

export const separatorFor = (path: string) => (path.toLowerCase().endsWith(".tsv") ? "\t" : ",");
