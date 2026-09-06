DROP INDEX IF EXISTS `idx_projects_local_path`;--> statement-breakpoint
DROP INDEX IF EXISTS `idx_projects_remote_path`;--> statement-breakpoint
DROP INDEX IF EXISTS `idx_projects_ssh_connection_id`;--> statement-breakpoint
DROP INDEX IF EXISTS `idx_workspaces_key`;--> statement-breakpoint
-- `projects.ssh_connection_id` participates in a foreign key constraint, so
-- SQLite cannot DROP COLUMN it — the table is recreated instead. The migration
-- runner disables foreign_keys around the transaction, so the DROP TABLE below
-- does not cascade into child tables.
CREATE TABLE `__new_projects` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`base_ref` text,
	`repository_workspace_id` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`deleted_at` text
);--> statement-breakpoint
INSERT INTO `__new_projects` (
	`id`, `name`, `base_ref`, `repository_workspace_id`, `created_at`, `updated_at`, `deleted_at`
)
SELECT `id`, `name`, `base_ref`, `repository_workspace_id`, `created_at`, `updated_at`, `deleted_at`
FROM `projects`;--> statement-breakpoint
DROP TABLE `projects`;--> statement-breakpoint
ALTER TABLE `__new_projects` RENAME TO `projects`;--> statement-breakpoint
CREATE UNIQUE INDEX `idx_projects_repository_workspace_id` ON `projects` (`repository_workspace_id`) WHERE "projects"."repository_workspace_id" IS NOT NULL AND "projects"."deleted_at" IS NULL;--> statement-breakpoint
ALTER TABLE `tasks` DROP COLUMN `workspace_provider`;--> statement-breakpoint
ALTER TABLE `tasks` DROP COLUMN `workspace_provider_data`;--> statement-breakpoint
ALTER TABLE `tasks` DROP COLUMN `workspace_intent`;--> statement-breakpoint
ALTER TABLE `workspaces` DROP COLUMN `key`;--> statement-breakpoint
ALTER TABLE `workspaces` DROP COLUMN `data`;--> statement-breakpoint
ALTER TABLE `workspaces` DROP COLUMN `branch_name`;