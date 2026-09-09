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

function normalizeUrlPath(value) {
  const normalized = String(value || "").trim().replace(/\\/g, "/").replace(/\/+$/, "");
  return normalized.replace(/^\/+/, "");
}

export function normalizeCadFileQueryParam(value) {
  return normalizeUrlPath(value);
}

function sourceExtensionForPath(value) {
  const match = /\.([^.\/]+)$/.exec(String(value || "").trim());
  return match ? `.${match[1]}` : "";
}

function appendExtension(value, extension) {
  const normalizedValue = normalizeUrlPath(value);
  const normalizedExtension = String(extension || "").trim();
  if (!normalizedValue || !normalizedExtension) {
    return normalizedValue;
  }
  return normalizedValue.toLowerCase().endsWith(normalizedExtension.toLowerCase())
    ? normalizedValue
    : `${normalizedValue}${normalizedExtension}`;
}

function fileAliasesForEntry(entry) {
  const aliases = new Set();
  const addAlias = (value) => {
    const normalizedValue = normalizeUrlPath(value);
    if (normalizedValue) {
      aliases.add(normalizedValue);
    }
  };

  const file = cadFileParamForEntry(entry);
  addAlias(file);

  const cadPath = cadPathForEntry(entry);
  const extension = sourceExtensionForPath(file);
  addAlias(appendExtension(cadPath, extension));

  return aliases;
}

export function findEntryByUrlPath(entries, urlPath) {
  const normalizedUrlPath = normalizeCadFileQueryParam(urlPath);
  if (!normalizedUrlPath) {
    return null;
  }
  return entries.find((entry) => fileAliasesForEntry(entry).has(normalizedUrlPath)) || null;
}

function entryLeafName(entry) {
  const file = fileKey(entry);
  if (!file) {
    return "";
  }
  const parts = file.split("/");
  return parts[parts.length - 1] || file;
}

export function sidebarDirectoryIdForEntry(entry) {
  const file = String(entry?.rootRelativeFile || fileKey(entry) || "").trim();
  const parts = file.split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
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
