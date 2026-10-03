import { FileSheetCheckboxRow, FileSheetSettingsSection } from "../inspector/FileSheet.js";

/**
 * The host's own on/off settings (`appSettings`) as Settings sections, one per `section` they
 * name, in the order they come: each an always-open section of checkbox rows.
 * @param {readonly import("../../../file-viewer/types.js").AppSetting[]} appSettings
 */
export function appSettingsSections(appSettings = []) {
  const groups = new Map();
  for (const setting of appSettings) groups.set(setting.section, [...(groups.get(setting.section) || []), setting]);
  return [...groups].map(([title, settings]) => ({
    id: `app-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`, title,
    content: settings.map(setting => <FileSheetCheckboxRow key={setting.id} label={setting.label} checked={setting.checked}
      disabled={setting.disabled} onCheckedChange={setting.onCheckedChange} />),
  }));
}

/** The host's settings as the Settings popover shows them, in the viewer and on the home alike. */
export function AppSettingsSections({ appSettings }) {
  return <div className="[&_[data-settings-section-heading]_.text-xs]:text-tiny" data-settings-sections="">
    {appSettingsSections(appSettings).map(section => <FileSheetSettingsSection key={section.id} sectionId={section.id} title={section.title}>
      {section.content}
    </FileSheetSettingsSection>)}
  </div>;
}
