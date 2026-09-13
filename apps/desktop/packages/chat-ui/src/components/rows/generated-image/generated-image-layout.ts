export type GeneratedImageGridMetrics = {
  columns: number;
  rows: number;
  tileSize: number;
  height: number;
};

export type GeneratedImageGridOptions = {
  gap: number;
  maxTileSize: number;
  minTwoColumnWidth: number;
};

/** Deterministic geometry shared by virtualized measurement and rendering. */
export function generatedImageGridMetrics(
  count: number,
  width: number,
  vars: GeneratedImageGridOptions
): GeneratedImageGridMetrics {
  if (count <= 0) return { columns: 0, rows: 0, tileSize: 0, height: 0 };
  const columns = count > 1 && width >= vars.minTwoColumnWidth ? 2 : 1;
  const available = Math.max(1, width - vars.gap * (columns - 1));
  const tileSize = Math.max(1, Math.min(vars.maxTileSize, Math.floor(available / columns)));
  const rows = Math.ceil(count / columns);
  return {
    columns,
    rows,
    tileSize,
    height: rows * tileSize + (rows - 1) * vars.gap,
  };
}
