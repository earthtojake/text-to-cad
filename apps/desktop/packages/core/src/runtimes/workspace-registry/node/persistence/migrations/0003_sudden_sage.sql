ALTER TABLE `workspace_records` ADD `personal_config` text;--> statement-breakpoint
ALTER TABLE `workspace_records` ADD `legacy_desktop_settings_migrated` integer DEFAULT false NOT NULL;