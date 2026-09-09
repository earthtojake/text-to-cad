CREATE TABLE `lifecycle_operations` (
	`id` text PRIMARY KEY NOT NULL,
	`kind` text NOT NULL,
	`status` text NOT NULL,
	`project_id` text,
	`task_id` text,
	`workspace_id` text,
	`entity_key` text,
	`host_ref` text NOT NULL,
	`payload` text NOT NULL,
	`attempt` integer DEFAULT 0 NOT NULL,
	`error` text,
	`created_at` integer NOT NULL,
	`finished_at` integer
);
--> statement-breakpoint
ALTER TABLE `projects` ADD `deleted_at` text;--> statement-breakpoint
ALTER TABLE `tasks` ADD `deleted_at` text;--> statement-breakpoint
ALTER TABLE `workspaces` ADD `deleted_at` text;--> statement-breakpoint
CREATE INDEX `idx_lifecycle_operations_status` ON `lifecycle_operations` (`status`);--> statement-breakpoint
CREATE INDEX `idx_lifecycle_operations_host_status` ON `lifecycle_operations` (`host_ref`,`status`);--> statement-breakpoint
CREATE INDEX `idx_lifecycle_operations_entity_key` ON `lifecycle_operations` (`entity_key`);