export function fileKey(entry) {
  return String(entry?.file || "").trim();
}
