CREATE TABLE `path_entries` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`root_id` integer NOT NULL,
	`generation` integer NOT NULL,
	`relative_path` text NOT NULL,
	`name` text NOT NULL,
	`kind` text NOT NULL,
	FOREIGN KEY (`root_id`) REFERENCES `registered_roots`(`id`) ON UPDATE no action ON DELETE cascade,
	CONSTRAINT "path_entries_generation_check" CHECK("path_entries"."generation" >= 1),
	CONSTRAINT "path_entries_relative_path_check" CHECK(length("path_entries"."relative_path") > 0),
	CONSTRAINT "path_entries_name_check" CHECK(length("path_entries"."name") > 0),
	CONSTRAINT "path_entries_kind_check" CHECK("path_entries"."kind" IN ('file', 'directory'))
);
--> statement-breakpoint
CREATE UNIQUE INDEX `path_entries_root_generation_path_idx` ON `path_entries` (`root_id`,`generation`,`relative_path`);--> statement-breakpoint
CREATE TABLE `registered_roots` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`root_key` text NOT NULL,
	`root_path` text NOT NULL,
	`current_generation` integer,
	CONSTRAINT "registered_roots_root_key_check" CHECK(length("registered_roots"."root_key") > 0),
	CONSTRAINT "registered_roots_root_path_check" CHECK(length("registered_roots"."root_path") > 0),
	CONSTRAINT "registered_roots_current_generation_check" CHECK("registered_roots"."current_generation" >= 1)
);
--> statement-breakpoint
CREATE UNIQUE INDEX `registered_roots_root_key_idx` ON `registered_roots` (`root_key`);