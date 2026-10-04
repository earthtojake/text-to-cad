export function fileKey(entry) {
  return String(entry?.file || "").trim();
}

export function cadPathForEntry(entry) {
  return fileKey(entry).replace(/\.(step|stp|stl|3mf|glb|dxf|urdf|srdf|sdf)$/i, "");
}
