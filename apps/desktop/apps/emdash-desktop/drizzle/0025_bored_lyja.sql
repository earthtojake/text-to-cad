CREATE TABLE `operation_claims` (
	`operation_id` text NOT NULL,
	`resource_key` text NOT NULL,
	PRIMARY KEY(`operation_id`, `resource_key`),
	FOREIGN KEY (`operation_id`) REFERENCES `lifecycle_operations`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
ALTER TABLE `lifecycle_operations` ADD `parent_operation_id` text;--> statement-breakpoint
ALTER TABLE `lifecycle_operations` ADD `initiated_by` text;--> statement-breakpoint
CREATE INDEX `idx_operation_claims_resource` ON `operation_claims` (`resource_key`);--> statement-breakpoint
CREATE INDEX `idx_lifecycle_operations_parent_status` ON `lifecycle_operations` (`parent_operation_id`,`status`);