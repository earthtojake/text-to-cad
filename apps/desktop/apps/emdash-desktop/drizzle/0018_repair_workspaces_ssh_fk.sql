CREATE TABLE `__new_workspaces` (
	`id` text PRIMARY KEY NOT NULL,
	`key` text,
	`type` text NOT NULL,
	`kind` text,
	`location` text,
	`ssh_connection_id` text,
	`data` text,
	`path` text,
	`config` text,
	`branch_name` text,
	`lines_added` integer,
	`lines_deleted` integer,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`ssh_connection_id`) REFERENCES `ssh_connections`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
INSERT INTO `__new_workspaces` (
	`id`,
	`key`,
	`type`,
	`kind`,
	`location`,
	`ssh_connection_id`,
	`data`,
	`path`,
	`config`,
	`branch_name`,
	`lines_added`,
	`lines_deleted`,
	`created_at`,
	`updated_at`
)
SELECT
	`id`,
	`key`,
	`type`,
	`kind`,
	`location`,
	CASE
		WHEN `ssh_connection_id` IS NULL THEN NULL
		WHEN EXISTS (
			SELECT 1
			FROM `ssh_connections`
			WHERE `ssh_connections`.`id` = `workspaces`.`ssh_connection_id`
		) THEN `ssh_connection_id`
		ELSE NULL
	END,
	`data`,
	`path`,
	`config`,
	`branch_name`,
	`lines_added`,
	`lines_deleted`,
	`created_at`,
	`updated_at`
FROM `workspaces`;
--> statement-breakpoint
DROP TABLE `workspaces`;
--> statement-breakpoint
ALTER TABLE `__new_workspaces` RENAME TO `workspaces`;
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_workspaces_key` ON `workspaces` (`key`) WHERE "workspaces"."key" is not null;
