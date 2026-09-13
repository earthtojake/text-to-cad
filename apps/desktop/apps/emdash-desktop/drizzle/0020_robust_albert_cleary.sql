CREATE TABLE `notifications` (
	`id` text PRIMARY KEY NOT NULL,
	`kind` text NOT NULL,
	`group_key` text NOT NULL,
	`title` text NOT NULL,
	`body` text NOT NULL,
	`payload` text NOT NULL,
	`count` integer DEFAULT 1 NOT NULL,
	`created_at` integer NOT NULL,
	`read_at` integer
);
--> statement-breakpoint
CREATE INDEX `idx_notifications_created_at` ON `notifications` (`created_at`);--> statement-breakpoint
CREATE INDEX `idx_notifications_group_key` ON `notifications` (`group_key`);--> statement-breakpoint
CREATE INDEX `idx_notifications_read_at` ON `notifications` (`read_at`);