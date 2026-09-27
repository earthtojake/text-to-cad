// Shared by interactive and headless material passes. A caller can supply or
// replace record colors, so only reuse a color whose private ownership we know.
const ownedEmissiveColors = new WeakMap();

export function syncRecordBaseEmissiveColor(record) {
  if (!record.baseColor) {
    record.baseEmissiveColor = null;
    ownedEmissiveColors.delete(record);
    return;
  }
  let color = ownedEmissiveColors.get(record);
  if (!color || color !== record.baseEmissiveColor || color === record.baseColor || color === record.sourceColor) {
    color = record.baseColor.clone();
    ownedEmissiveColors.set(record, color);
  } else {
    color.copy(record.baseColor);
  }
  record.baseEmissiveColor = color;
}
