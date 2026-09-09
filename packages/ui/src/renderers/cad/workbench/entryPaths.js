export function fileKey(entry) {
  return String(entry?.file || "").trim();
}

export function cadFileParamForEntry(entry) {
  const file = fileKey(entry);
  const rootRelativeFile = String(entry?.rootRelativeFile || "").trim();
  return rootRelativeFile || file;
}

export function cadPathForEntry(entry) {
  const file = cadFileParamForEntry(entry);
  return file.replace(/\.(step|stp|stl|3mf|glb|dxf|urdf|srdf|sdf)$/i, "");
}

function entryLeafName(entry) {
  const file = fileKey(entry);
  if (!file) {
    return "";
  }
  const parts = file.split("/");
  return parts[parts.length - 1] || file;
}

export function filenameLabelForEntry(entry) {
  // The entry's REAL filename on disk, never a reconstruction and never a substitution.
  //
  // Two rules used to live here and both lied about what the user was looking at. The first
  // rebuilt a label from a stem plus a canonical extension, so `gasket_plate.dxf.py` showed
  // as `gasket_plate.dxf` and an imported drawing beside it was indistinguishable. The
  // second preferred the recorded generator path, so `moonwatch.step` — a real file, sitting
  // right there — showed as `moonwatch.py`, a file that does not even live in that directory
  // any more now that model scripts moved into `src/`.
  //
  // An artifact is presented as an artifact: every user-visible name is the basename of the
  // catalog entry's own path. Generated-vs-imported still drives status badges and rebuild
  // behaviour; it never drives the NAME. Showing the filename verbatim also means new source
  // kinds need no case here.
  return entryLeafName(entry);
}

export function sidebarLabelForEntry(entry) {
  return filenameLabelForEntry(entry);
}
