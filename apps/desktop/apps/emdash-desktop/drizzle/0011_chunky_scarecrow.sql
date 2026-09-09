CREATE TABLE `workspaces` (
	`id` text PRIMARY KEY NOT NULL,
	`key` text,
	`type` text NOT NULL,
	`data` text,
	`path` text,
	`lines_added` integer,
	`lines_deleted` integer,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_workspaces_key` ON `workspaces` (`key`) WHERE "workspaces"."key" is not null;