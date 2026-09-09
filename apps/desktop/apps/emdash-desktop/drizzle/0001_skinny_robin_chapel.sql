CREATE TABLE `app_secrets` (
	`key` text PRIMARY KEY NOT NULL,
	`secret` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_app_secrets_key` ON `app_secrets` (`key`);