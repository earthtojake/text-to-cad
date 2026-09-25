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
  return entries.find((entry) => normalizeUrlPath(cadFileParamForEntry(entry)) === normalizedUrlPath) || null;
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
