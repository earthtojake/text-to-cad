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

export function writeCadParam(urlPath, { history = "replace" } = {}) {
  if (typeof window === "undefined") {
    return;
  }
  const normalizedUrlPath = normalizeCadFileQueryParam(urlPath);
  const url = new URL(window.location.href);
  // Only the file changes here. The directory lives in the URL's path and is never
  // rewritten from the client — switching directories means navigating to a new URL.
  if (normalizedUrlPath) {
    url.searchParams.set(CAD_QUERY_PARAM, normalizedUrlPath);
  } else {
    url.searchParams.delete(CAD_QUERY_PARAM);
  }
  writeUrl(url, { history });
}
