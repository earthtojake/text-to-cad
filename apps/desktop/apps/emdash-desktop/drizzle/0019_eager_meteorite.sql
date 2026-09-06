CREATE TABLE `provider_accounts` (
	`id` text PRIMARY KEY NOT NULL,
	`provider_id` text NOT NULL,
	`account_id` text NOT NULL,
	`credential_ref` text NOT NULL,
	`is_default` integer DEFAULT false NOT NULL,
	`meta` text,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_provider_accounts_provider_account` ON `provider_accounts` (`provider_id`,`account_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `idx_provider_accounts_default` ON `provider_accounts` (`provider_id`) WHERE is_default = 1;