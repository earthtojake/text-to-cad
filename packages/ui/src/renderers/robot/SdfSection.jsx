import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { useI18n } from "@text-to-cad/ui/i18n";
import { useViewerMobile } from "../../file-viewer/responsive.js";
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
  const { t } = useI18n();
  const records = Array.isArray(items) ? items.map(item => formatSdfMetadataItem(item, fields)).filter(Boolean) : [];
  if (!records.length) return null;
  return (
    <div className="space-y-1.5 rounded-md border border-border/80 bg-background/40 p-2">
      <span className={FILE_SHEET_FIELD_LABEL_CLASSES}>{title}</span>
      <div className="space-y-1">
        {records.slice(0, 5).map((record, index) => (
          <TooltipHint key={`${title}:${index}`} content={record} overflowOnly><div  className="truncate text-tiny leading-4 text-foreground" >{record}</div></TooltipHint>
        ))}
        {records.length > 5 ? <div className="text-tiny leading-4 text-muted-foreground">{t("sdf.more", { count: records.length - 5 })}</div> : null}
      </div>
    </div>
  );
}

/**
 * What an SDF document says about itself beyond its links and joints: the payload's `sdf` record.
 * Its counts are three tiles a row; on a phone, whose panel is 288px wide and whose type is a step
 * larger, two, so "Nested models" and "Unsupported geom." read whole instead of truncating.
 */
export default function SdfSection({ info }) {
  const { t } = useI18n();
  const mobile = useViewerMobile();
  const sdfInfo = info && typeof info === "object" ? info : {};
  const metadata = sdfInfo.staticMetadata && typeof sdfInfo.staticMetadata === "object" ? sdfInfo.staticMetadata : {};
  const list = key => (Array.isArray(metadata[key]) ? metadata[key] : []);
  const includes = list("includes"), plugins = list("plugins"), sensors = list("sensors"), lights = list("lights"), physics = list("physics");
  const nestedModelCount = Number.isFinite(Number(metadata.nestedModelCount)) ? Number(metadata.nestedModelCount) : 0;
  return (
    <div>
      <FileSheetSubsection title={t("sdf.document")}>
        <FileSheetFieldGrid columns={2}>
          <FileSheetValueField label={t("sdf.version")} value={String(sdfInfo.version || t("sdf.unknown"))} />
          <FileSheetValueField label={t("sdf.document")} value={String(sdfInfo.documentKind || "model")} />
          {sdfInfo.worldName ? <FileSheetValueField label={t("sdf.world")} value={String(sdfInfo.worldName)} /> : null}
          {/* A model whose links float free has no single root: each is listed. */}
          <FileSheetValueField label={t("robot.rootLink")} value={String(sdfInfo.rootLink || (Array.isArray(sdfInfo.rootLinks) ? sdfInfo.rootLinks.join(", ") : ""))} />
          <FileSheetValueField label={t("sdf.model")} value={String(sdfInfo.modelName || "SDF")} />
        </FileSheetFieldGrid>
      </FileSheetSubsection>
      <FileSheetSubsection title={t("sdf.counts")}>
        <FileSheetFieldGrid columns={mobile ? 2 : 3} data-sdf-counts="">
          <FileSheetValueField label={t("robot.links")} value={String(sdfInfo.linkCount ?? 0)} />
          <FileSheetValueField label={t("sdf.joints")} value={String(sdfInfo.jointCount ?? 0)} />
          <FileSheetValueField label={t("sdf.frames")} value={String(sdfInfo.frameCount ?? 0)} />
          <FileSheetValueField label={t("sdf.includes")} value={String(includes.length)} />
          <FileSheetValueField label={t("sdf.plugins")} value={String(plugins.length)} />
          <FileSheetValueField label={t("sdf.sensors")} value={String(sensors.length)} />
          <FileSheetValueField label={t("sdf.lights")} value={String(lights.length)} />
          <FileSheetValueField label={t("sdf.physics")} value={String(physics.length)} />
          <FileSheetValueField label={t("sdf.nestedModels")} value={formatSdfNumber(nestedModelCount)} />
          {/* The collisions whose geometry the viewer cannot draw: counted, never refused. */}
          <FileSheetValueField label={t("sdf.unsupportedGeometry")} value={formatSdfNumber(sdfInfo.unsupportedCollisionCount)} />
        </FileSheetFieldGrid>
      </FileSheetSubsection>
      {includes.length || plugins.length || sensors.length || lights.length || physics.length ? (
        <FileSheetSubsection title={t("sdf.metadata")} contentClassName="px-2">
          <SdfMetadataList title={t("sdf.includes")} items={includes} fields={["name", "uri"]} />
          <SdfMetadataList title={t("sdf.plugins")} items={plugins} fields={["name", "filename"]} />
          <SdfMetadataList title={t("sdf.sensors")} items={sensors} fields={["name", "type"]} />
          <SdfMetadataList title={t("sdf.lights")} items={lights} fields={["name", "type"]} />
          <SdfMetadataList title={t("sdf.physics")} items={physics} fields={["name", "type", "default"]} />
        </FileSheetSubsection>
      ) : null}
    </div>
  );
}
