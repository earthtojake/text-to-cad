import { FILE_SHEET_FIELD_LABEL_CLASSES, FileSheetFieldGrid, FileSheetSubsection, FileSheetValueField } from "../kit/inspector/FileSheet.js";

function formatSdfNumber(value, fallback = "0") {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return fallback;
  const rounded = Math.round(numericValue * 1000) / 1000;
  return String(Object.is(rounded, -0) ? 0 : rounded);
}

function formatSdfMetadataItem(item, fields) {
  if (!item || typeof item !== "object") return "";
  return fields.map(field => String(item?.[field] || "").trim()).filter(Boolean).join(" / ");
}

function SdfMetadataList({ title, items, fields }) {
  const records = Array.isArray(items) ? items.map(item => formatSdfMetadataItem(item, fields)).filter(Boolean) : [];
  if (!records.length) return null;
  return (
    <div className="space-y-1.5 rounded-md border border-border/80 bg-background/40 p-2">
      <span className={FILE_SHEET_FIELD_LABEL_CLASSES}>{title}</span>
      <div className="space-y-1">
        {records.slice(0, 5).map((record, index) => (
          <div key={`${title}:${index}`} className="truncate text-tiny leading-4 text-foreground" title={record}>{record}</div>
        ))}
        {records.length > 5 ? <div className="text-tiny leading-4 text-muted-foreground">{records.length - 5} more</div> : null}
      </div>
    </div>
  );
}

/** What an SDF document says about itself beyond its links and joints: the parser's `sdf` record. */
export default function SdfTab({ info, movableJointCount = 0, title = "SDF" }) {
  const sdfInfo = info && typeof info === "object" ? info : {};
  const metadata = sdfInfo.staticMetadata && typeof sdfInfo.staticMetadata === "object" ? sdfInfo.staticMetadata : {};
  const list = key => (Array.isArray(metadata[key]) ? metadata[key] : []);
  const includes = list("includes"), plugins = list("plugins"), sensors = list("sensors"), lights = list("lights"), physics = list("physics");
  const nestedModelCount = Number.isFinite(Number(metadata.nestedModelCount)) ? Number(metadata.nestedModelCount) : 0;
  return (
    <div>
      <FileSheetSubsection title="Document">
        <FileSheetFieldGrid columns={2}>
          <FileSheetValueField label="Version" value={String(sdfInfo.version || "unknown")} />
          <FileSheetValueField label="Document" value={String(sdfInfo.documentKind || "model")} />
          {sdfInfo.worldName ? <FileSheetValueField label="World" value={String(sdfInfo.worldName)} /> : null}
          <FileSheetValueField label="Frame mode" value={sdfInfo.nativeFrameSemantics ? "native" : "compat"} />
          <FileSheetValueField label="Root link" value={String(sdfInfo.rootLink || "")} />
          <FileSheetValueField label="Model" value={String(sdfInfo.modelName || title || "model")} />
        </FileSheetFieldGrid>
      </FileSheetSubsection>
      <FileSheetSubsection title="Counts">
        <FileSheetFieldGrid columns={3}>
          <FileSheetValueField label="Links" value={String(sdfInfo.linkCount ?? movableJointCount)} />
          <FileSheetValueField label="Joints" value={String(sdfInfo.jointCount ?? movableJointCount)} />
          <FileSheetValueField label="Frames" value={String(sdfInfo.frameCount ?? 0)} />
          <FileSheetValueField label="Includes" value={String(includes.length)} />
          <FileSheetValueField label="Plugins" value={String(plugins.length)} />
          <FileSheetValueField label="Sensors" value={String(sensors.length)} />
          <FileSheetValueField label="Lights" value={String(lights.length)} />
          <FileSheetValueField label="Physics" value={String(physics.length)} />
          <FileSheetValueField label="Nested models" value={formatSdfNumber(nestedModelCount)} />
          <FileSheetValueField label="Unsupported geom." value={`${formatSdfNumber(sdfInfo.unsupportedVisualCount)} / ${formatSdfNumber(sdfInfo.unsupportedCollisionCount)}`} />
        </FileSheetFieldGrid>
      </FileSheetSubsection>
      {includes.length || plugins.length || sensors.length || lights.length || physics.length ? (
        <FileSheetSubsection title="Metadata" contentClassName="px-2">
          <SdfMetadataList title="Includes" items={includes} fields={["name", "uri"]} />
          <SdfMetadataList title="Plugins" items={plugins} fields={["name", "filename"]} />
          <SdfMetadataList title="Sensors" items={sensors} fields={["name", "type"]} />
          <SdfMetadataList title="Lights" items={lights} fields={["name", "type"]} />
          <SdfMetadataList title="Physics" items={physics} fields={["name", "type", "default"]} />
        </FileSheetSubsection>
      ) : null}
    </div>
  );
}
