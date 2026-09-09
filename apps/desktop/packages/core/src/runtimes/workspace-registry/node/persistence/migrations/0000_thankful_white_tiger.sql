CREATE TABLE `workspace_records` (
	`id` text PRIMARY KEY NOT NULL,
	`kind` text NOT NULL,
	`path` text NOT NULL,
	`parent_id` text,
	`origin` text NOT NULL,
	`git_admin_name` text,
	`observed_status` text NOT NULL,
	`creation` text,
	`last_create_outcome` text,
	`git` text,
	`last_activated_at` integer,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	`last_observed_at` integer NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `workspace_records_path_unique` ON `workspace_records` (`path`);