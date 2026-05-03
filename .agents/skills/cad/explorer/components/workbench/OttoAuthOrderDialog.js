import { useEffect, useMemo, useState } from "react";
import { ExternalLink, LoaderCircle } from "lucide-react";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle
} from "../ui/alert-dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";
import {
  buildCadProjectPackage,
  buildCadProjectPackageSummary,
  buildEntryDownloadUrl,
  buildOttoAuthCartReturnUrl,
  buildOttoAuthConnectUrl,
  buildOttoAuthOrderUrl,
  buildOttoAuthTaskPayload,
  entryDisplayLabel,
  entryFormatLabel,
  normalizeOttoAuthBaseUrl,
  OTTOAUTH_AGENT_TASK_PROXY_ENDPOINT,
  OTTOAUTH_FILE_UPLOAD_PROXY_ENDPOINT,
  OTTOAUTH_LOCAL_AGENT_PROXY_ENDPOINT,
  OTTOAUTH_ME_PROXY_ENDPOINT,
} from "../../lib/ottoAuth";

const fieldLabelClasses = "block text-xs font-medium text-muted-foreground";
const compactInputClasses = "h-8 text-xs font-medium";
const selectClasses =
  "border-input bg-transparent text-foreground h-8 w-full rounded-md border px-2 text-xs font-medium shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50";

const SUPPLIER_OPTIONS = [
  { id: "auto", label: "Auto select", name: "", url: "" },
  { id: "craftcloud", label: "Craftcloud", name: "Craftcloud", url: "https://craftcloud3d.com/upload" },
  { id: "xometry", label: "Xometry", name: "Xometry", url: "https://www.xometry.com/" },
  { id: "protolabs", label: "Protolabs", name: "Protolabs", url: "https://www.protolabs.com/" },
  { id: "sendcutsend", label: "SendCutSend", name: "SendCutSend", url: "https://sendcutsend.com/" },
  { id: "pcbway", label: "PCBWay", name: "PCBWay", url: "https://www.pcbway.com/" },
  { id: "jlcpcb", label: "JLCPCB", name: "JLCPCB", url: "https://jlcpcb.com/" },
  { id: "mcmaster", label: "McMaster-Carr", name: "McMaster-Carr", url: "https://www.mcmaster.com/" },
  { id: "misumi", label: "MISUMI", name: "MISUMI", url: "https://us.misumi-ec.com/" },
  { id: "digikey", label: "Digi-Key", name: "Digi-Key", url: "https://www.digikey.com/" },
  { id: "mouser", label: "Mouser", name: "Mouser", url: "https://www.mouser.com/" },
  { id: "custom", label: "Custom supplier", name: "", url: "" }
];

function emptyForm() {
  return {
    quantity: "1",
    material: "",
    supplierId: "auto",
    supplierName: "",
    supplierUrl: "",
    maxSpendUsd: "",
    packageSummary: "",
    notes: ""
  };
}

function selectedEntryKey(entry) {
  return String(entry?.file || entry?.name || entry?.source?.path || entry?.step?.path || "");
}

function errorMessageForResponse(payload, statusCode, ottoAuthBaseUrl) {
  const upstreamMessage = String(payload?.error || payload?.message || "").trim();
  if (statusCode === 401) {
    return `Sign in to OttoAuth at ${ottoAuthBaseUrl}/login, then retry.`;
  }
  if (statusCode === 404) {
    return "OttoAuth submission is available from the local CAD Explorer dev server.";
  }
  return upstreamMessage || `OttoAuth request failed with status ${statusCode}.`;
}

function formatUsd(cents) {
  const value = Number(cents);
  if (!Number.isFinite(value)) {
    return "$0.00";
  }
  return `$${(value / 100).toFixed(2)}`;
}

async function readJsonResponse(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return { error: text };
  }
}

function fileNameFromCadFile(file, index) {
  const label = String(file?.label || file?.key || `cad-file-${index + 1}`).trim();
  return label.split(/[\\/]/).filter(Boolean).pop() || `cad-file-${index + 1}`;
}

async function uploadCadProjectPackage(cadPackage) {
  const cadFiles = Array.isArray(cadPackage?.cadFiles) ? cadPackage.cadFiles : [];
  const uploadTargets = cadFiles.filter((file) => String(file?.url || "").trim()).slice(0, 20);
  if (!uploadTargets.length) {
    return cadPackage;
  }

  const formData = new FormData();
  const metadata = [];
  for (let index = 0; index < uploadTargets.length; index += 1) {
    const file = uploadTargets[index];
    const response = await fetch(file.url, { credentials: "same-origin" });
    if (!response.ok) {
      throw new Error(`Could not read ${file.label || file.url} for OttoAuth upload.`);
    }
    const blob = await response.blob();
    formData.append("file", blob, fileNameFromCadFile(file, index));
    metadata.push({
      source: "cad-explorer",
      original_url: file.url,
      label: file.label,
      key: file.key,
      format: file.format,
      selected: Boolean(file.selected)
    });
  }
  formData.append("metadata", JSON.stringify({ app_id: "cad-explorer", files: metadata }));

  const response = await fetch(OTTOAUTH_FILE_UPLOAD_PROXY_ENDPOINT, {
    method: "POST",
    credentials: "include",
    body: formData
  });
  const payload = await readJsonResponse(response);
  if (!response.ok) {
    throw new Error(payload?.error || `OttoAuth file upload failed with status ${response.status}.`);
  }

  const uploadedFiles = Array.isArray(payload?.files) ? payload.files : [];
  let uploadIndex = 0;
  const uploadedCadFiles = cadFiles.map((file) => {
    if (!String(file?.url || "").trim() || uploadIndex >= uploadedFiles.length) {
      return file;
    }
    const uploaded = uploadedFiles[uploadIndex];
    uploadIndex += 1;
    return {
      ...file,
      local_url: file.url,
      url: uploaded?.url || file.url,
      ottoauth_file_id: uploaded?.id || "",
      ottoauth_sha256: uploaded?.sha256 || "",
      size: uploaded?.size ?? file.size
    };
  });
  const selectedFile = uploadedCadFiles.find((file) => file.selected) || uploadedCadFiles[0] || null;

  return {
    ...cadPackage,
    selectedFile,
    cadFiles: uploadedCadFiles,
    primarySourceUrl: selectedFile?.url || uploadedCadFiles.find((file) => file.url)?.url || cadPackage.primarySourceUrl || ""
  };
}

export default function OttoAuthOrderDialog({
  open,
  onOpenChange,
  selectedEntry,
  catalogEntries = [],
  assemblyParts = [],
  selectedPartIds = [],
  catalogRootDir = "",
  onStatus
}) {
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [account, setAccount] = useState(null);
  const [localAgent, setLocalAgent] = useState(null);
  const [accountLoading, setAccountLoading] = useState(false);
  const [agentLoading, setAgentLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const entryKey = selectedEntryKey(selectedEntry);
  const entryLabel = entryDisplayLabel(selectedEntry);
  const entryFormat = selectedEntry ? entryFormatLabel(selectedEntry) : "";
  const ottoAuthBaseUrl = normalizeOttoAuthBaseUrl(import.meta.env?.EXPLORER_OTTOAUTH_BASE_URL);
  const cadProjectPackage = useMemo(() => {
    const origin = typeof window === "undefined" ? "" : window.location.origin;
    return buildCadProjectPackage({
      entries: catalogEntries,
      selectedEntry,
      assemblyParts,
      selectedPartIds,
      origin,
      catalogRootDir
    });
  }, [assemblyParts, catalogEntries, catalogRootDir, selectedEntry, selectedPartIds]);
  const sourceUrl = useMemo(() => {
    return cadProjectPackage.primarySourceUrl || buildEntryDownloadUrl(selectedEntry, {
      origin: typeof window === "undefined" ? "" : window.location.origin,
      catalogRootDir
    });
  }, [cadProjectPackage.primarySourceUrl, catalogRootDir, selectedEntry]);

  useEffect(() => {
    if (!open) {
      return;
    }
    setForm({
      ...emptyForm(),
      packageSummary: buildCadProjectPackageSummary(cadProjectPackage)
    });
    setError("");
    setAccount(null);
    setLocalAgent(null);
    setSubmitting(false);
  }, [cadProjectPackage, entryKey, open]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const controller = new AbortController();
    async function loadAccount() {
      setAccountLoading(true);
      setError("");
      try {
        const response = await fetch(OTTOAUTH_ME_PROXY_ENDPOINT, {
          method: "GET",
          headers: {
            "Accept": "application/json"
          },
          credentials: "include",
          signal: controller.signal
        });
        const payload = await readJsonResponse(response);
        if (response.status === 401) {
          setAccount(null);
          return;
        }
        if (!response.ok) {
          setError(errorMessageForResponse(payload, response.status, ottoAuthBaseUrl));
          return;
        }
        setAccount(payload);

        setAccountLoading(false);
        setAgentLoading(true);
        const agentResponse = await fetch(OTTOAUTH_LOCAL_AGENT_PROXY_ENDPOINT, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json"
          },
          credentials: "include",
          body: JSON.stringify({
            app_id: "cad-explorer",
            app_name: "CAD Explorer",
            agent_name: "CAD Explorer local coding agent"
          }),
          signal: controller.signal
        });
        const agentPayload = await readJsonResponse(agentResponse);
        if (!agentResponse.ok) {
          setError(errorMessageForResponse(agentPayload, agentResponse.status, ottoAuthBaseUrl));
          return;
        }
        setLocalAgent(agentPayload);
      } catch (requestError) {
        if (requestError instanceof DOMException && requestError.name === "AbortError") {
          return;
        }
        setError(requestError instanceof Error ? requestError.message : "Could not reach OttoAuth.");
      } finally {
        setAccountLoading(false);
        setAgentLoading(false);
      }
    }

    void loadAccount();
    return () => {
      controller.abort();
    };
  }, [open, ottoAuthBaseUrl]);

  const updateForm = (key, value) => {
    setForm((current) => ({
      ...current,
      [key]: value
    }));
  };

  const connectToOttoAuth = () => {
    const currentUrl = typeof window === "undefined"
      ? ""
      : buildOttoAuthCartReturnUrl(window.location.href);
    if (typeof window !== "undefined") {
      window.location.href = buildOttoAuthConnectUrl(ottoAuthBaseUrl, currentUrl);
    }
  };

  const handleSupplierChange = (supplierId) => {
    const supplier = SUPPLIER_OPTIONS.find((option) => option.id === supplierId) || SUPPLIER_OPTIONS[0];
    setForm((current) => ({
      ...current,
      supplierId: supplier.id,
      supplierName: supplier.name,
      supplierUrl: supplier.url
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");

    if (!account?.user) {
      connectToOttoAuth();
      return;
    }

    if (!localAgent?.agent?.username) {
      setError("OttoAuth is still preparing linked agent credentials. Try again in a moment.");
      return;
    }

    if (!selectedEntry && !String(form.notes || "").trim()) {
      setError("Enter request details when no CAD file is selected.");
      return;
    }

    setSubmitting(true);
    let uploadedPackage;
    try {
      uploadedPackage = await uploadCadProjectPackage(cadProjectPackage);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Could not upload CAD files to OttoAuth.");
      setSubmitting(false);
      return;
    }

    const payload = buildOttoAuthTaskPayload({
      entry: selectedEntry,
      sourceUrl: uploadedPackage.primarySourceUrl || sourceUrl,
      form: {
        ...form,
        packageSummary: buildCadProjectPackageSummary(uploadedPackage),
        cadFiles: uploadedPackage.cadFiles,
        cadParts: uploadedPackage.parts
      }
    });

    try {
      const response = await fetch(OTTOAUTH_AGENT_TASK_PROXY_ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        credentials: "include",
        body: JSON.stringify(payload)
      });
      const responsePayload = await readJsonResponse(response);
      if (!response.ok) {
        setError(errorMessageForResponse(responsePayload, response.status, ottoAuthBaseUrl));
        return;
      }

      const taskId = String(responsePayload?.task?.id || "").trim();
      onStatus?.(taskId ? "OttoAuth order queued" : "OttoAuth request submitted");
      onOpenChange?.(false);
      if (taskId && typeof window !== "undefined") {
        window.location.href = buildOttoAuthOrderUrl(ottoAuthBaseUrl, taskId);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not reach OttoAuth.");
    } finally {
      setSubmitting(false);
    }
  };

  const user = account?.user || null;
  const displayName = String(user?.display_name || user?.email || "OttoAuth").trim();
  const connectedEmail = String(user?.email || "").trim();
  const balanceLabel = formatUsd(account?.balance_cents);
  const agentUsername = String(localAgent?.agent?.username || "").trim();
  const credentialPath = String(localAgent?.credential_path || "").trim();

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="max-h-[min(42rem,calc(100vh-2rem))] max-w-xl overflow-y-auto">
        <form className="grid gap-4" onSubmit={handleSubmit}>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {user ? "Buy Parts Now" : "Connect OttoAuth Account"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {user
                ? "Review the auto-filled CAD package, choose a supplier, then send it to OttoAuth."
                : "Create or sign in to OttoAuth, then register this local coding agent for one-click orders."}
            </AlertDialogDescription>
          </AlertDialogHeader>

          <div className="rounded-md border border-border/70 bg-muted/30 px-3 py-2 text-xs">
            <div className="flex min-w-0 items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="font-medium text-foreground">
                  {entryLabel || "Current CAD project"}
                </div>
                <div className="mt-0.5 text-muted-foreground">
                  {selectedEntry ? `${entryFormat} from ${cadProjectPackage.cadFiles.length} project file${cadProjectPackage.cadFiles.length === 1 ? "" : "s"}` : `${cadProjectPackage.cadFiles.length} project file${cadProjectPackage.cadFiles.length === 1 ? "" : "s"}`}
                </div>
              </div>
              {sourceUrl ? (
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-foreground hover:bg-accent hover:text-accent-foreground"
                >
                  <ExternalLink className="size-3" aria-hidden="true" />
                  Source
                </a>
              ) : null}
            </div>
          </div>

          {error ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs font-medium text-destructive">
              {error}
            </div>
          ) : null}

          <div className="rounded-md border border-border/70 bg-muted/20 px-3 py-2 text-xs">
            {accountLoading ? (
              <div className="flex items-center gap-2 font-medium text-muted-foreground">
                <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
                Checking OttoAuth connection...
              </div>
            ) : user ? (
              <div className="grid gap-2">
                <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-medium text-foreground">Logged in as {displayName}</div>
                    {connectedEmail && connectedEmail !== displayName ? (
                      <div className="mt-0.5 text-muted-foreground">{connectedEmail}</div>
                    ) : null}
                  </div>
                  <div className="rounded-md bg-accent px-2 py-1 font-medium text-accent-foreground">
                    {balanceLabel} credits
                  </div>
                </div>
                {agentLoading ? (
                  <div className="flex items-center gap-2 font-medium text-muted-foreground">
                    <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
                    Linking local coding agent...
                  </div>
                ) : agentUsername ? (
                  <div className="rounded-md border border-border/70 bg-background px-2 py-1.5 text-muted-foreground">
                    Agent @{agentUsername} linked to this OttoAuth account
                    {credentialPath ? `; saved to ${credentialPath}` : ""}.
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="grid gap-2">
                <div className="font-medium text-foreground">
                  Connect your OttoAuth account
                </div>
                <div className="text-muted-foreground">
                  OttoAuth will create or find your account, then register this computer's local coding agent so future orders can be submitted through the agent API.
                </div>
                <Button type="button" size="sm" onClick={connectToOttoAuth} className="justify-self-start">
                  Connect OttoAuth
                </Button>
              </div>
            )}
          </div>

          {user ? (
            <>
          <div className="grid gap-3 sm:grid-cols-[5.5rem_minmax(0,1fr)]">
            <label className="block">
              <span className={fieldLabelClasses}>Quantity</span>
              <Input
                type="number"
                min="1"
                step="1"
                inputMode="numeric"
                value={form.quantity}
                onChange={(event) => updateForm("quantity", event.target.value)}
                className={`${compactInputClasses} mt-1.5`}
              />
            </label>
            <label className="block min-w-0">
              <span className={fieldLabelClasses}>Material or finish</span>
              <Input
                value={form.material}
                onChange={(event) => updateForm("material", event.target.value)}
                placeholder="6061 aluminum, PETG, black oxide, M3 stainless"
                className={`${compactInputClasses} mt-1.5`}
              />
            </label>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block min-w-0">
              <span className={fieldLabelClasses}>Supplier</span>
              <select
                value={form.supplierId}
                onChange={(event) => handleSupplierChange(event.target.value)}
                className={`${selectClasses} mt-1.5`}
              >
                {SUPPLIER_OPTIONS.map((supplier) => (
                  <option key={supplier.id} value={supplier.id}>
                    {supplier.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block min-w-0">
              <span className={fieldLabelClasses}>Supplier URL</span>
              <Input
                value={form.supplierUrl}
                onChange={(event) => updateForm("supplierUrl", event.target.value)}
                placeholder="Optional supplier link"
                className={`${compactInputClasses} mt-1.5`}
              />
            </label>
          </div>

          {form.supplierId === "custom" ? (
            <label className="block min-w-0">
              <span className={fieldLabelClasses}>Custom supplier name</span>
              <Input
                value={form.supplierName}
                onChange={(event) => updateForm("supplierName", event.target.value)}
                placeholder="Supplier or fabrication service name"
                className={`${compactInputClasses} mt-1.5`}
              />
            </label>
          ) : null}

          <label className="block">
            <span className={fieldLabelClasses}>CAD package sent to OttoAuth</span>
            <Textarea
              value={form.packageSummary}
              onChange={(event) => updateForm("packageSummary", event.target.value)}
              className="mt-1.5 min-h-48 font-mono text-[11px] leading-4"
            />
          </label>

          <label className="block max-w-xs min-w-0">
            <span className={fieldLabelClasses}>Spend cap</span>
            <Input
              value={form.maxSpendUsd}
              onChange={(event) => updateForm("maxSpendUsd", event.target.value)}
              placeholder="Optional USD"
              inputMode="decimal"
              className={`${compactInputClasses} mt-1.5`}
            />
          </label>

          <label className="block">
            <span className={fieldLabelClasses}>Request details</span>
            <Textarea
              value={form.notes}
              onChange={(event) => updateForm("notes", event.target.value)}
              placeholder="Tolerances, substitute parts, shipping preferences, or exact vendor instructions."
              className="mt-1.5 min-h-24 text-xs"
            />
          </label>

          <AlertDialogFooter>
            <AlertDialogCancel type="button" disabled={submitting}>
              Cancel
            </AlertDialogCancel>
            <Button type="submit" disabled={submitting || accountLoading || agentLoading}>
              {submitting ? (
                <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              ) : null}
              {submitting ? "Sending..." : "One-click buy"}
            </Button>
          </AlertDialogFooter>
            </>
          ) : (
            <AlertDialogFooter>
              <AlertDialogCancel type="button">Cancel</AlertDialogCancel>
              <Button type="button" onClick={connectToOttoAuth} disabled={accountLoading}>
                Connect OttoAuth
              </Button>
            </AlertDialogFooter>
          )}
        </form>
      </AlertDialogContent>
    </AlertDialog>
  );
}
