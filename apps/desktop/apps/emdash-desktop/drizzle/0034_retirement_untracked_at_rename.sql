ALTER TABLE `workspaces` RENAME COLUMN `deleted_at` TO `untracked_at`;--> statement-breakpoint
DROP INDEX IF EXISTS `idx_workspaces_local_path`;--> statement-breakpoint
DROP INDEX IF EXISTS `idx_workspaces_remote_path`;--> statement-breakpoint
CREATE UNIQUE INDEX `idx_workspaces_local_path` ON `workspaces` (`path`) WHERE "workspaces"."location" = 'local' AND "workspaces"."untracked_at" IS NULL AND "workspaces"."path" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `idx_workspaces_remote_path` ON `workspaces` (`ssh_connection_id`,`path`) WHERE "workspaces"."location" = 'remote' AND "workspaces"."untracked_at" IS NULL AND "workspaces"."path" IS NOT NULL;