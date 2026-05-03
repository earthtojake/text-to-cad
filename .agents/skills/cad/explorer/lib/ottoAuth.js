export const DEFAULT_OTTOAUTH_BASE_URL = "http://localhost:3000";
export const OTTOAUTH_ME_PROXY_ENDPOINT = "/__ottoauth/me";
export const OTTOAUTH_LOCAL_AGENT_PROXY_ENDPOINT = "/__ottoauth/local-agent";
export const OTTOAUTH_AGENT_TASK_PROXY_ENDPOINT = "/__ottoauth/agent-task";
export const OTTOAUTH_FILE_UPLOAD_PROXY_ENDPOINT = "/__ottoauth/files";

const FILE_EXTENSION_FORMATS = new Map([
  ["step", "STEP"],
  ["stp", "STEP"],
  ["stl", "STL"],
  ["3mf", "3MF"],
  ["dxf", "DXF"],
  ["urdf", "URDF"]
]);

function normalizeRelativePath(value) {
  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return "";
  }
  return rawValue
    .replace(/\\/g, "/")
    .replace(/^\/+/, "")
    .replace(/\/+$/, "");
}

function normalizeCatalogRootDir(value) {
  const normalized = normalizeRelativePath(value);
  if (!normalized || normalized === ".") {
    return "";
  }
  return normalized;
}

function joinRelativePath(...parts) {
  return parts
    .map(normalizeRelativePath)
    .filter(Boolean)
    .join("/");
}

function encodeUrlPath(relativePath) {
  const normalized = normalizeRelativePath(relativePath);
  if (!normalized) {
    return "";
  }
  return `/${normalized.split("/").map((part) => encodeURIComponent(part)).join("/")}`;
}

function stripQueryAndHash(value) {
  return String(value || "").split(/[?#]/)[0];
}

function defaultBaseUrlForBrowser() {
  if (typeof window === "undefined" || !window.location?.hostname) {
    return DEFAULT_OTTOAUTH_BASE_URL;
  }
  const protocol = window.location.protocol === "https:" ? "https:" : "http:";
  return `${protocol}//${window.location.hostname}:3000`;
}

export function normalizeOttoAuthBaseUrl(value, fallback = defaultBaseUrlForBrowser()) {
  const rawValue = String(value || "").trim();
  const candidate = rawValue || fallback || DEFAULT_OTTOAUTH_BASE_URL;
  try {
    const url = new URL(candidate);
    url.pathname = url.pathname.replace(/\/+$/, "");
    url.search = "";
    url.hash = "";
    return url.toString().replace(/\/+$/, "");
  } catch {
    return DEFAULT_OTTOAUTH_BASE_URL;
  }
}

export function parseUsdToCents(value) {
  const normalized = String(value || "").trim().replace(/[^0-9.]/g, "");
  if (!normalized) {
    return null;
  }
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return Math.round(parsed * 100);
}

export function entrySourceFormat(entry) {
  const kind = String(entry?.kind || "").trim().toLowerCase();
  if (kind === "part" || kind === "assembly") {
    return "step";
  }
  if (kind === "stp") {
    return "step";
  }
  if (FILE_EXTENSION_FORMATS.has(kind)) {
    return kind;
  }
  const path = String(entry?.source?.path || entry?.step?.path || entry?.file || "").trim();
  const extension = stripQueryAndHash(path).split(".").pop()?.toLowerCase() || "";
  if (extension === "stp") {
    return "step";
  }
  return FILE_EXTENSION_FORMATS.has(extension) ? extension : "";
}

export function entryFormatLabel(entry) {
  const format = entrySourceFormat(entry);
  return FILE_EXTENSION_FORMATS.get(format) || "CAD";
}

export function entryDisplayLabel(entry) {
  return String(entry?.name || entry?.file || entry?.source?.path || entry?.step?.path || "").trim();
}

function entrySourcePath(entry, catalogRootDir = "") {
  if (!entry) {
    return "";
  }
  const format = entrySourceFormat(entry);
  if (format === "step") {
    const rootDir = normalizeCatalogRootDir(catalogRootDir);
    const sourcePath = normalizeRelativePath(entry?.step?.path || entry?.source?.path || entry?.file);
    if (!sourcePath) {
      return "";
    }
    if (rootDir && (sourcePath === rootDir || sourcePath.startsWith(`${rootDir}/`))) {
      return sourcePath;
    }
    return joinRelativePath(rootDir, sourcePath);
  }
  return normalizeRelativePath(entry?.source?.path || entry?.file);
}

export function buildEntryDownloadUrl(entry, { origin = "", catalogRootDir = "" } = {}) {
  const safeOrigin = String(origin || "").trim();
  if (!entry || !safeOrigin) {
    return "";
  }

  const format = entrySourceFormat(entry);
  const assetUrl = String(entry?.assets?.[format]?.url || "").trim();
  const sourceUrl = assetUrl || encodeUrlPath(entrySourcePath(entry, catalogRootDir));
  if (!sourceUrl) {
    return "";
  }

  try {
    return new URL(sourceUrl, safeOrigin).href;
  } catch {
    return "";
  }
}

function uniqueBy(items, keyForItem) {
  const seen = new Set();
  const result = [];
  for (const item of Array.isArray(items) ? items : []) {
    const key = String(keyForItem(item) || "").trim();
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(item);
  }
  return result;
}

function normalizePartLabel(part) {
  return String(part?.name || part?.displayName || part?.label || part?.sourcePath || part?.id || "").trim();
}

function normalizePartRecord(part) {
  const id = String(part?.id || "").trim();
  const label = normalizePartLabel(part);
  if (!id && !label) {
    return null;
  }
  return {
    id,
    label: label || id,
    sourcePath: String(part?.sourcePath || "").trim(),
    occurrenceId: String(part?.occurrenceId || "").trim()
  };
}

export function buildCadProjectPackage({
  entries = [],
  selectedEntry = null,
  assemblyParts = [],
  selectedPartIds = [],
  origin = "",
  catalogRootDir = ""
} = {}) {
  const selectedKey = String(selectedEntry?.file || selectedEntry?.name || selectedEntry?.source?.path || selectedEntry?.step?.path || "").trim();
  const projectEntries = uniqueBy(
    [
      selectedEntry,
      ...entries
    ].filter(Boolean),
    (entry) => entry?.file || entry?.name || entry?.source?.path || entry?.step?.path
  );
  const selectedPartIdSet = new Set(
    (Array.isArray(selectedPartIds) ? selectedPartIds : [])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const normalizedParts = uniqueBy(
    (Array.isArray(assemblyParts) ? assemblyParts : [])
      .filter((part) => !selectedPartIdSet.size || selectedPartIdSet.has(String(part?.id || "").trim()))
      .map(normalizePartRecord)
      .filter(Boolean),
    (part) => part.id || part.label
  );
  const fallbackParts = normalizedParts.length
    ? normalizedParts
    : uniqueBy(
      (Array.isArray(assemblyParts) ? assemblyParts : [])
        .map(normalizePartRecord)
        .filter(Boolean),
      (part) => part.id || part.label
    );
  const cadFiles = projectEntries.map((entry) => {
    const key = String(entry?.file || entry?.name || entry?.source?.path || entry?.step?.path || "").trim();
    return {
      key,
      label: entryDisplayLabel(entry) || key,
      format: entryFormatLabel(entry),
      selected: Boolean(selectedKey && key === selectedKey),
      url: buildEntryDownloadUrl(entry, { origin, catalogRootDir })
    };
  });
  const selectedFile = cadFiles.find((file) => file.selected) || cadFiles[0] || null;

  return {
    selectedFile,
    cadFiles,
    parts: fallbackParts,
    selectedPartCount: normalizedParts.length,
    primarySourceUrl: selectedFile?.url || cadFiles.find((file) => file.url)?.url || ""
  };
}

export function buildCadProjectPackageSummary(cadPackage = {}) {
  const selectedFile = cadPackage?.selectedFile || null;
  const cadFiles = Array.isArray(cadPackage?.cadFiles) ? cadPackage.cadFiles : [];
  const parts = Array.isArray(cadPackage?.parts) ? cadPackage.parts : [];
  const selectedPartCount = Number(cadPackage?.selectedPartCount || 0);
  const cadFileLines = cadFiles
    .slice(0, 24)
    .map((file, index) => `${index + 1}. ${file.label}${file.format ? ` (${file.format})` : ""}${file.url ? ` - ${file.url}` : ""}`);
  const partLines = parts
    .slice(0, 40)
    .map((part, index) => {
      const sourceSuffix = part.sourcePath ? ` - source ${part.sourcePath}` : "";
      return `${index + 1}. ${part.label}${sourceSuffix}`;
    });

  return [
    "CAD project package:",
    selectedFile ? `Selected CAD file: ${selectedFile.label}${selectedFile.format ? ` (${selectedFile.format})` : ""}` : "Selected CAD file: none",
    selectedFile?.url ? `Selected CAD URL: ${selectedFile.url}` : "",
    cadFileLines.length ? `Project CAD files (${cadFiles.length}${cadFiles.length > cadFileLines.length ? `, first ${cadFileLines.length} shown` : ""}):\n${cadFileLines.join("\n")}` : "Project CAD files: none discovered",
    partLines.length ? `Assembly parts (${parts.length}${selectedPartCount ? `, ${selectedPartCount} selected` : ""}${parts.length > partLines.length ? `, first ${partLines.length} shown` : ""}):\n${partLines.join("\n")}` : "Assembly parts: none discovered"
  ].filter(Boolean).join("\n");
}

export function buildOttoAuthOrderUrl(baseUrl, taskId = "") {
  const normalizedBaseUrl = normalizeOttoAuthBaseUrl(baseUrl);
  const normalizedTaskId = String(taskId || "").trim();
  if (normalizedTaskId) {
    return `${normalizedBaseUrl}/orders/${encodeURIComponent(normalizedTaskId)}`;
  }
  return `${normalizedBaseUrl}/orders/new`;
}

export function buildOttoAuthConnectUrl(baseUrl, returnUrl = "", {
  appId = "cad-explorer",
  appName = "CAD Explorer"
} = {}) {
  const normalizedBaseUrl = normalizeOttoAuthBaseUrl(baseUrl);
  const targetUrl = new URL("/api/sdk/connect", `${normalizedBaseUrl}/`);
  targetUrl.searchParams.set("app_id", appId);
  targetUrl.searchParams.set("app_name", appName);
  if (returnUrl) {
    targetUrl.searchParams.set("return_to", returnUrl);
  }
  return targetUrl.href;
}

export function buildOttoAuthLoginUrl(baseUrl, returnUrl = "") {
  return buildOttoAuthConnectUrl(baseUrl, returnUrl);
}

export function buildOttoAuthCartReturnUrl(currentUrl) {
  try {
    const url = new URL(String(currentUrl || ""));
    url.searchParams.set("ottoauthCart", "1");
    return url.href;
  } catch {
    return "";
  }
}

function normalizeQuantity(value) {
  const parsed = Number.parseInt(String(value || "").trim(), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function normalizeText(value, limit = 1000) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, limit);
}

function normalizeMultilineText(value, limit = 8000) {
  return String(value || "")
    .replace(/\r\n?/g, "\n")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
    .slice(0, limit);
}

function normalizeUrl(value) {
  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return "";
  }
  try {
    return new URL(rawValue).href;
  } catch {
    if (/^[a-z][a-z0-9+.-]*:/i.test(rawValue)) {
      return rawValue;
    }
    try {
      return new URL(`https://${rawValue}`).href;
    } catch {
      return rawValue;
    }
  }
}

export function buildOttoAuthTaskPrompt({
  entry = null,
  sourceUrl = "",
  form = {}
} = {}) {
  const entryLabel = entryDisplayLabel(entry);
  const quantity = normalizeQuantity(form.quantity);
  const formatLabel = entry ? entryFormatLabel(entry) : "";
  const material = normalizeText(form.material, 300);
  const supplierName = normalizeText(form.supplierName, 160);
  const supplierUrl = normalizeUrl(form.supplierUrl);
  const packageSummary = normalizeMultilineText(form.packageSummary, 8000);
  const notes = normalizeText(form.notes, 1800);
  const sourceLine = sourceUrl ? `CAD source URL: ${sourceUrl}` : "";
  const selectedLine = entryLabel
    ? `Selected CAD file: ${entryLabel}${formatLabel ? ` (${formatLabel})` : ""}`
    : "Selected CAD file: none";
  const targetLine = supplierName || supplierUrl
    ? `Preferred supplier or manufacturing service: ${[supplierName, supplierUrl].filter(Boolean).join(" ")}`
    : "Find a suitable supplier, fabrication service, or manufacturing quote flow.";

  return [
    `Please buy or source ${quantity} physical part${quantity === 1 ? "" : "s"} for this CAD project.`,
    selectedLine,
    sourceLine,
    targetLine,
    material ? `Material, process, or finish preference: ${material}` : "",
    packageSummary,
    "If this is a custom geometry, use the CAD source URL when a supplier or manufacturing service asks for the model. If it appears to be off-the-shelf hardware, find the closest purchasable matching part.",
    "Use the linked OttoAuth human account's saved shipping and payment context. Do not ask for card numbers or CVV in chat; if checkout needs new payment credentials or missing address/contact details, request clarification through OttoAuth instead of guessing.",
    notes ? `Additional request details: ${notes}` : ""
  ].filter(Boolean).join("\n");
}

export function buildOttoAuthTaskPayload({
  entry = null,
  sourceUrl = "",
  form = {}
} = {}) {
  const supplierUrl = normalizeUrl(form.supplierUrl);
  const supplierName = normalizeText(form.supplierName, 160);
  const maxChargeCents = parseUsdToCents(form.maxSpendUsd);
  const entryLabel = entryDisplayLabel(entry) || "CAD project";
  const cadFiles = Array.isArray(form.cadFiles) ? form.cadFiles : [];
  const cadParts = Array.isArray(form.cadParts) ? form.cadParts : [];
  const payload = {
    app_id: "cad-explorer",
    kind: "buy_parts",
    task: buildOttoAuthTaskPrompt({ entry, sourceUrl, form }),
    task_title: `Buy parts: ${entryLabel}`.slice(0, 120),
    platform_hint: "parts supplier or manufacturing service",
    confirmation_mode: "auto_purchase_under_cap",
    url_policy: supplierUrl ? "preferred" : "discover",
    request_source: "cad-explorer",
    cad_file: entryLabel,
    files: cadFiles,
    ottoauth_files: cadFiles,
    cad_files: cadFiles,
    cad_parts: cadParts,
    cad_source_url: sourceUrl || null,
    quantity: normalizeQuantity(form.quantity)
  };

  if (supplierName) {
    payload.merchant_name = supplierName;
  }
  if (supplierUrl) {
    payload.url = supplierUrl;
  }
  if (maxChargeCents != null) {
    payload.max_charge_cents = maxChargeCents;
  }
  return payload;
}
