CREATE TABLE `project_settings` (
	`project_id` text PRIMARY KEY NOT NULL,
	`base_project_settings_json` text DEFAULT '{}' NOT NULL,
	`shareable_project_settings_json` text DEFAULT '{}' NOT NULL,
	`legacy_config_migrated_at` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON UPDATE no action ON DELETE cascade
);
