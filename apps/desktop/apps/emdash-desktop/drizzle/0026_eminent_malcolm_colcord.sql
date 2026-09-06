ALTER TABLE `lifecycle_operations` ADD `parent_forget_policy` text;--> statement-breakpoint
ALTER TABLE `lifecycle_operations` ADD `confirmed_at` integer;--> statement-breakpoint
ALTER TABLE `lifecycle_operations` ADD `confirmation_reason` text;