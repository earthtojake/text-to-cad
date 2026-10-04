export function fileKey(entry) {
  return String(entry?.file || "").trim();
}

export function cadFileParamForEntry(entry) {
  return fileKey(entry);
}

export function cadPathForEntry(entry) {
  const file = cadFileParamForEntry(entry);
  return file.replace(/\.(step|stp|stl|3mf|glb|dxf|urdf|srdf|sdf)$/i, "");
}
