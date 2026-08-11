import { normalizeViewerDefaultFile } from "../../shared/viewerConfig.mjs";

const CAD_QUERY_PARAM = "file";

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

function writeUrl(url, { history = "replace" } = {}) {
  const nextSearch = url.searchParams.toString();
  const nextUrl = `${url.pathname}${nextSearch ? `?${nextSearch}` : ""}${url.hash}`;
  const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (nextUrl === currentUrl) {
    return false;
  }
  if (history === "push" && typeof window.history?.pushState === "function") {
    window.history.pushState({}, "", nextUrl);
  } else {
    window.history.replaceState({}, "", nextUrl);
  }
  return true;
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

export function readDefaultCadParam() {
  return normalizeViewerDefaultFile(import.meta.env?.VIEWER_DEFAULT_FILE) || null;
}

export function readCadParam() {
  if (typeof window === "undefined") {
    return null;
  }
  const params = new URLSearchParams(window.location.search);
  const value = params.get(CAD_QUERY_PARAM);
  const normalizedValue = typeof value === "string"
    ? normalizeCadFileQueryParam(value)
    : "";
  return normalizedValue || null;
}


export function findEntryByUrlPath(entries, urlPath) {
  const normalizedUrlPath = normalizeCadFileQueryParam(urlPath);
  if (!normalizedUrlPath) {
    return null;
  }
  return entries.find((entry) => fileAliasesForEntry(entry).has(normalizedUrlPath)) || null;
}

export function shouldDeferFileParamSelection({
  explicitFileParam = "",
  matchingEntry = null,
  selectedEntry = null,
  catalogHydrated = false,
  catalogRefreshing = false
} = {}) {
  const normalizedFileParam = normalizeCadFileQueryParam(explicitFileParam);
  if (!normalizedFileParam || selectedEntry) {
    return false;
  }
  if (matchingEntry) {
    return true;
  }
  return !catalogHydrated || catalogRefreshing;
}

export function missingFileRefForCatalog({
  explicitFileParam = "",
  matchingEntry = null,
  selectedEntry = null,
  catalogHydrated = false,
  catalogRefreshing = false
} = {}) {
  const normalizedFileParam = normalizeCadFileQueryParam(explicitFileParam);
  if (
    !normalizedFileParam ||
    selectedEntry ||
    matchingEntry ||
    !catalogHydrated ||
    catalogRefreshing
  ) {
    return "";
  }
  return normalizedFileParam;
}

export function selectedEntryKeyFromUrl(entries, { defaultFile = readDefaultCadParam() } = {}) {
  const explicitFilePath = readCadParam();
  if (explicitFilePath) {
    const match = findEntryByUrlPath(entries, explicitFilePath);
    return match ? fileKey(match) : "";
  }

  const match = findEntryByUrlPath(entries, normalizeCadFileQueryParam(defaultFile));
  return match ? fileKey(match) : "";
}

export function writeCadParam(urlPath, { history = "replace" } = {}) {
  if (typeof window === "undefined") {
    return;
  }
  const normalizedUrlPath = normalizeCadFileQueryParam(urlPath);
  const url = new URL(window.location.href);
  url.searchParams.delete("refs");
  // Only the file changes here. The directory lives in the URL's path and is never
  // rewritten from the client — switching directories means navigating to a new URL.
  if (normalizedUrlPath) {
    url.searchParams.set(CAD_QUERY_PARAM, normalizedUrlPath);
  } else {
    url.searchParams.delete(CAD_QUERY_PARAM);
  }
  writeUrl(url, { history });
}

function compareSidebarLabels(a, b) {
  return String(a || "").localeCompare(String(b || ""), undefined, {
    numeric: true,
    sensitivity: "base"
  });
}

function entryLeafName(entry) {
  const file = fileKey(entry);
  if (!file) {
    return "";
  }
  const parts = file.split("/");
  return parts[parts.length - 1] || file;
}

function sourceLeafName(entry) {
  const source = entry?.source;
  const candidate = String(
    entry?.sourcePath
    || (source && typeof source === "object" ? (source.sourcePath || source.path || source.file) : "")
    || ""
  ).trim();
  if (!candidate) {
    return "";
  }
  const parts = candidate.split("/");
  return parts[parts.length - 1] || "";
}

function normalizedEntryStem(entry) {
  return entryLeafName(entry)
    .replace(/\.step\.json$/i, "")
    .replace(/\.urdf\.json$/i, "")
    // A generator entry's filename is `<name>.step.py` / `<name>.dxf.py` — strip the whole
    // generator suffix to `<name>` so the label reconstructs as `<name>.step` / `<name>.dxf`
    // (not `<name>.step.step` or `<name>.dxf.dxf`).
    .replace(/\.(step|stp|dxf)\.py$/i, "")
    .replace(/\.(step|stp|stl|3mf|glb|dxf|urdf|srdf|sdf|py)$/i, "");
}

export function sidebarDirectoryIdForEntry(entry) {
  const file = String(entry?.rootRelativeFile || fileKey(entry) || "").trim();
  const parts = file.split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
}

function sourceExtensionForEntry(entry) {
  const leafName = entryLeafName(entry);
  const match = /\.([^.]+)$/.exec(leafName);
  return String(match?.[1] || "").trim().toLowerCase();
}

export function filenameLabelForEntry(entry) {
  // The entry's REAL filename, never a reconstruction.
  //
  // This used to rebuild a label from a stem plus a canonical extension, which erased what
  // the file is actually called: `gasket_plate.dxf.py` displayed as `gasket_plate.dxf`, so a
  // generated drawing and an imported one beside it were indistinguishable in the explorer,
  // the breadcrumb and the tab. Two different files, one label — and the one you clicked was
  // whichever the list happened to hold.
  //
  // Showing the filename verbatim also means new source kinds need no case here.
  //
  // Prefer the recorded SOURCE path over `file`: a generated model can carry its logical
  // output there (`<stem>.step`) while the file a user edits is the generator beside it.
  // The source path is what they opened, so it is what the label should say.
  return sourceLeafName(entry) || entryLeafName(entry);
}

export function sidebarLabelForEntry(entry) {
  return filenameLabelForEntry(entry);
}

function compareSidebarEntries(a, b) {
  const nameDiff = sidebarLabelForEntry(a).localeCompare(sidebarLabelForEntry(b), undefined, {
    numeric: true,
    sensitivity: "base"
  });
  if (nameDiff !== 0) {
    return nameDiff;
  }
  return fileKey(a).localeCompare(fileKey(b), undefined, {
    numeric: true,
    sensitivity: "base"
  });
}

function createSidebarDirectoryNode(id, name) {
  return {
    id,
    name,
    entries: [],
    children: new Map()
  };
}

function finalizeSidebarDirectoryNode(node) {
  return {
    id: node.id,
    name: node.name,
    entries: [...node.entries].sort(compareSidebarEntries),
    directories: [...node.children.values()]
      .map(finalizeSidebarDirectoryNode)
      .sort((a, b) => compareSidebarLabels(a.name, b.name))
  };
}

export function buildSidebarDirectoryTree(entries, { rootName = "Directory" } = {}) {
  const root = createSidebarDirectoryNode("", String(rootName || "Directory"));

  for (const entry of entries) {
    const directoryId = sidebarDirectoryIdForEntry(entry);
    const directoryParts = directoryId ? directoryId.split("/") : [];
    let currentNode = root;
    let currentId = "";

    for (const part of directoryParts) {
      currentId = currentId ? `${currentId}/${part}` : part;
      const childNode = currentNode.children.get(part) || createSidebarDirectoryNode(currentId, part);
      currentNode.children.set(part, childNode);
      currentNode = childNode;
    }

    currentNode.entries.push(entry);
  }

  return finalizeSidebarDirectoryNode(root);
}

export function collectSidebarDirectoryIds(directoryNode, result = []) {
  for (const directory of directoryNode.directories || []) {
    result.push(directory.id);
    collectSidebarDirectoryIds(directory, result);
  }
  return result;
}

export function findSidebarDirectoryById(directoryNode, directoryId) {
  const targetId = String(directoryId || "").trim();
  if (!directoryNode) {
    return null;
  }
  if (String(directoryNode.id || "") === targetId) {
    return directoryNode;
  }

  for (const childDirectory of directoryNode.directories || []) {
    const match = findSidebarDirectoryById(childDirectory, targetId);
    if (match) {
      return match;
    }
  }

  return null;
}

export function sidebarDirectoryPath(directoryNode, directoryId) {
  const targetId = String(directoryId || "").trim();
  if (!directoryNode) {
    return [];
  }
  if (!targetId) {
    return [directoryNode];
  }

  const result = [];
  const visit = (node) => {
    result.push(node);
    if (String(node.id || "") === targetId) {
      return true;
    }

    for (const childDirectory of node.directories || []) {
      if (visit(childDirectory)) {
        return true;
      }
    }

    result.pop();
    return false;
  };

  return visit(directoryNode) ? result : [];
}

export function listSidebarItems(directory) {
  return [
    ...(directory.directories || []).map((childDirectory) => ({
      type: "directory",
      key: `directory:${childDirectory.id}`,
      label: childDirectory.name,
      value: childDirectory
    })),
    ...(directory.entries || []).map((entry) => ({
      type: "entry",
      key: `entry:${fileKey(entry)}`,
      label: sidebarLabelForEntry(entry),
      value: entry
    }))
  ].sort((a, b) => {
    const labelDiff = compareSidebarLabels(a.label, b.label);
    if (labelDiff !== 0) {
      return labelDiff;
    }
    return a.key.localeCompare(b.key, undefined, {
      numeric: true,
      sensitivity: "base"
    });
  });
}

export function collectAncestorDirectoryIds(directoryId) {
  if (!directoryId) {
    return [];
  }

  const parts = String(directoryId).split("/").filter(Boolean);
  const ancestorIds = [];
  let currentId = "";

  for (const part of parts) {
    currentId = currentId ? `${currentId}/${part}` : part;
    ancestorIds.push(currentId);
  }

  return ancestorIds;
}
